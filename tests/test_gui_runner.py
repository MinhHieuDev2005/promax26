import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import gui


class RunnerTests(unittest.TestCase):
    def test_python_json_runner_can_be_registered_and_launched(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "registered.json"
            runner = Path(directory) / "solver.py"
            runner.touch()
            with patch.object(gui, "RUNNER_REGISTRY", registry), \
                    patch.dict(gui.CUSTOM_RUNNERS, {}, clear=True), patch.dict(gui.SOLVERS):
                label = gui.register_runner("Python", runner)
                self.assertEqual(gui.read_custom_runners(), {label: runner.resolve()})
                with self.assertRaisesRegex(ValueError, "Bot HTTP"):
                    gui.register_runner("Python", runner, "http")
                with patch.object(gui.subprocess, "run") as run:
                    run.return_value = subprocess.CompletedProcess([], 0, '{"ok":true,"roles":[0]}', "")
                    self.assertEqual(gui.run_runner({"op": "roles", "config": {"agents": [0]}}, 3, runner), [0])
                    self.assertEqual(run.call_args.args[0], [gui.sys.executable, str(runner.resolve())])

    def test_http_registration_replaces_json_mode_and_survives_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "registered.json"
            executable = Path(directory) / "bot.exe"
            executable.touch()
            with patch.object(gui, "RUNNER_REGISTRY", registry), patch.dict(gui.CUSTOM_RUNNERS, {}, clear=True), patch.dict(gui.SOLVERS):
                previous = gui.register_runner("Bot", executable)
                saved = registry.read_bytes()
                with patch.object(Path, "replace", side_effect=OSError("read-only")):
                    with self.assertRaises(OSError):
                        gui.register_runner("Bot", executable, "http")
                self.assertEqual(registry.read_bytes(), saved)
                self.assertIn(previous, gui.CUSTOM_RUNNERS)
                label = gui.register_runner("Bot", executable, "http")
                self.assertEqual(label, "HTTP: Bot")
                self.assertEqual(gui.read_custom_runners(), {label: executable.resolve()})
                self.assertNotIn(previous, gui.SOLVERS)
                self.assertNotIn(previous, gui.CUSTOM_RUNNERS)
                with self.assertRaises(ValueError):
                    gui.solve_roles(label, {})
                with self.assertRaises(ValueError):
                    gui.solve_plan(label, {}, {}, [])
                gui.unregister_runner(label)
                self.assertEqual(gui.read_custom_runners(), {})
                self.assertTrue(executable.exists())

    def test_http_launch_arguments_and_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "bot with spaces.exe"
            executable.touch()
            with patch.object(gui.subprocess, "Popen") as launch:
                gui.start_http_bot(executable, "https://example.test", "match-id", "secret-token")
                self.assertEqual(launch.call_args.args[0], [str(executable.resolve()), "-transport", "http", "-url", "https://example.test", "-match", "match-id", "-token", "secret-token"])
                self.assertEqual(launch.call_args.kwargs["cwd"], executable.parent.resolve())
                self.assertEqual(launch.call_args.kwargs["stdin"], subprocess.DEVNULL)
                self.assertNotIn("shell", launch.call_args.kwargs)
                launch.reset_mock()
                for url, match_id, token in [("file:///tmp/test", "match", "token"), ("https://user:pass@example.test", "match", "token"), ("https://example.test", "", "token"), ("https://example.test", "match", "bad\ntoken")]:
                    with self.assertRaises(ValueError):
                        gui.start_http_bot(executable, url, match_id, token)
                launch.assert_not_called()

    def test_http_live_dispatch_does_not_submit_from_gui(self):
        window = Mock()
        window.runner_changes_allowed.return_value = True
        window.ent_token.get.return_value = "secret"
        window.ent_match_id.get.return_value = "match-id"
        window.ent_host.get.return_value = "example.test"
        window.api.base_url = "https://example.test"
        window.cbo_solver.get.return_value = "HTTP: Bot"
        window.cbo_timelimit.get.return_value = "1500ms"
        window.cbo_role_preset.current.return_value = 2
        window.role_mode = "auto"
        window.get_selected_roles.return_value = [1, 0]
        window.http_process = None
        window.is_running = False
        with patch.dict(gui.CUSTOM_RUNNERS, {"HTTP: Bot": Path("bot.exe")}), patch.dict(gui.SOLVERS, {"HTTP: Bot": "HTTP: Bot"}), patch.object(gui, "start_http_bot") as launch, patch.object(gui.threading, "Thread") as thread, patch.object(gui.messagebox, "showinfo"):
            gui.HexControlCenter.start_live_match(window, mode="step")
            launch.assert_not_called()
            gui.HexControlCenter.start_live_match(window)
            launch.assert_not_called()
            self.assertEqual(thread.call_args.kwargs["target"], window._run_http_session)
            self.assertEqual(thread.call_args.kwargs["args"], (Path("bot.exe"), "https://example.test", "match-id", "secret", None))
            window.get_selected_roles.assert_not_called()
            window.cbo_role_preset.current.return_value = 0
            window.role_mode = "manual"
            gui.HexControlCenter.start_live_match(window)
            self.assertEqual(thread.call_args.kwargs["args"], (Path("bot.exe"), "https://example.test", "match-id", "secret", [1, 0]))
            window._run_live_worker.assert_not_called()
            window.api.submit_roles.assert_not_called()
            window.api.submit_actions.assert_not_called()

    def test_http_log_redacts_token_and_reports_exit(self):
        window = Mock()
        process = Mock(stdout=io.StringIO("hello secret-token local-secret\n"))
        process.wait.return_value = 2
        self.assertEqual(gui.HexControlCenter._read_http_output(window, process, "secret-token", "local-secret"), 2)
        window.log.assert_called_once_with("hello [TOKEN] [LOCAL TOKEN]", "INFO")

    def test_http_session_uses_proxy_and_cleans_up(self):
        window = Mock(stop_requested=False)
        window._read_http_output.return_value = 0
        proxy = Mock(url="http://127.0.0.1:12345", local_token="local-secret")
        with patch.object(gui, "BotProxy", return_value=proxy), patch.object(gui, "start_http_bot") as launch:
            gui.HexControlCenter._run_http_session(window, Path("bot.exe"), "https://example.test", "match", "secret", custom_roles=[1, 0])
            proxy.check_connection.assert_called_once()
            launch.assert_called_once_with(Path("bot.exe"), proxy.url, "match", "local-secret")
            proxy.close.assert_called_once()
            window.http_results.put.assert_called_once_with(0)
            launch.reset_mock()
            proxy.reset_mock()
            window.reset_mock()
            proxy.check_connection.side_effect = OSError("TLS verification failed")
            gui.HexControlCenter._run_http_session(window, Path("bot.exe"), "https://example.test", "match", "secret")
            launch.assert_not_called()
            proxy.close.assert_called_once()
            window.http_results.put.assert_called_once_with(-1)
            window.stop_requested = True
            proxy.reset_mock()
            gui.HexControlCenter._run_http_session(window, Path("bot.exe"), "https://example.test", "match", "secret")
            proxy.check_connection.assert_not_called()
            launch.assert_not_called()
            proxy.close.assert_called_once()

    def test_http_stop_uses_windows_process_tree(self):
        process = Mock(pid=12345)
        process.poll.return_value = None
        with patch.object(gui.os, "name", "nt"), patch.object(gui.subprocess, "CREATE_NO_WINDOW", 0, create=True), patch.object(gui.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as stop:
            gui.stop_http_bot(process)
            self.assertEqual(stop.call_args.args[0], ["taskkill", "/PID", "12345", "/T", "/F"])
            process.wait.assert_called_once_with(timeout=5)
            stop.return_value = subprocess.CompletedProcess([], 1)
            with self.assertRaises(RuntimeError):
                gui.stop_http_bot(process)
            stop.reset_mock()
            process.poll.return_value = 0
            gui.stop_http_bot(process)
            stop.assert_not_called()

    def test_removal_persists_without_deleting_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "registered.json"
            executable = Path(directory) / "solver.exe"
            executable.touch()
            with patch.object(gui, "RUNNER_REGISTRY", registry), patch.dict(gui.CUSTOM_RUNNERS, {}, clear=True), patch.dict(gui.SOLVERS):
                original = dict(gui.SOLVERS)
                first = gui.register_runner("First", executable)
                second = gui.register_runner("Second", executable)
                saved = registry.read_bytes()
                with patch.object(Path, "replace", side_effect=OSError("read-only")):
                    with self.assertRaises(OSError):
                        gui.unregister_runner(first)
                self.assertEqual(registry.read_bytes(), saved)
                self.assertIn(first, gui.CUSTOM_RUNNERS)
                self.assertIn(first, gui.SOLVERS)
                with self.assertRaises(ValueError):
                    gui.unregister_runner(next(iter(original)))
                gui.unregister_runner(first)
                self.assertEqual(gui.read_custom_runners(), {second: executable.resolve()})
                self.assertNotIn(first, gui.SOLVERS)
                self.assertNotIn(first, gui.CUSTOM_RUNNERS)
                gui.unregister_runner(second)
                self.assertEqual(gui.read_custom_runners(), {})
                self.assertEqual(gui.SOLVERS, original)
                self.assertTrue(executable.is_file())

    def test_registration_persists_and_preserves_existing_solvers(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "registered.json"
            first = Path(directory) / "first.exe"
            second = Path(directory) / "second.exe"
            first.touch()
            second.touch()
            with patch.object(gui, "RUNNER_REGISTRY", registry), patch.dict(gui.CUSTOM_RUNNERS, {}, clear=True), patch.dict(gui.SOLVERS):
                original = dict(gui.SOLVERS)
                first_label = gui.register_runner("First", first)
                second_label = gui.register_runner("Second", second)
                self.assertEqual(gui.read_custom_runners(), {first_label: first.resolve(), second_label: second.resolve()})
                self.assertTrue(original.items() <= gui.SOLVERS.items())
                self.assertEqual(gui.SOLVERS[first_label], first_label)
                gui.register_runner("First", second)
                self.assertEqual(gui.read_custom_runners()[first_label], second.resolve())
                saved = registry.read_bytes()
                with patch.object(Path, "replace", side_effect=OSError("read-only")):
                    with self.assertRaises(OSError):
                        gui.register_runner("First", first)
                self.assertEqual(registry.read_bytes(), saved)
                self.assertEqual(gui.CUSTOM_RUNNERS[first_label], second.resolve())
                for name, filename in [(" ", first), ("bad\nname", first), ("Missing", first.with_name("missing.exe"))]:
                    with self.assertRaises(ValueError):
                        gui.register_runner(name, filename)
                registry.write_text("[]", encoding="utf-8")
                with self.assertRaises(ValueError):
                    gui.register_runner("Third", first)
                self.assertEqual(registry.read_text(encoding="utf-8"), "[]")

    def test_dispatch_uses_each_registered_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            runners = {f"EXE: {name}": Path(directory) / f"{name}.exe" for name in ("First", "Second")}
            for executable in runners.values():
                executable.touch()
            with patch.dict(gui.CUSTOM_RUNNERS, runners, clear=True), patch.object(gui, "normalize_map_config"), patch.object(gui, "build_procon26_payload", return_value={"op": "plan", "state": {"agents": [{}, {}]}}), patch.object(gui.subprocess, "run") as run:
                for policy, executable in runners.items():
                    run.return_value = subprocess.CompletedProcess([], 0, '{"ok":true,"roles":[1,0]}', "")
                    self.assertEqual(gui.solve_roles(policy, {"agents": [0, 1]}), [1, 0])
                    self.assertEqual(run.call_args.args[0], [str(executable.resolve())])
                    run.return_value = subprocess.CompletedProcess([], 0, '{"ok":true,"plan":[[-20],[-20]]}', "")
                    self.assertEqual(gui.solve_plan(policy, {}, {}, [1, 0]), [[-20], [-20]])
                    self.assertEqual(run.call_args.args[0], [str(executable.resolve())])

    def test_auto_race_all_includes_registered_runners(self):
        executable = Path("custom.exe")
        plan = [[-20]]
        response = {"ok": True, "plan": plan, "planner_state": {"warm": 1}}
        context = gui.new_runner_context()
        with patch.dict(gui.CUSTOM_RUNNERS, {"EXE: Custom": executable, "HTTP: Bot": Path("http.exe")}, clear=True), patch.object(gui, "normalize_map_config"), patch.object(gui, "run_runner", return_value=response) as runner, patch.object(gui, "check_plan_score", return_value={"valid": True, "servings": 1}), patch.object(gui.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, json.dumps(plan), "")):
            self.assertEqual(gui.solve_auto_race(
                {}, {"agents": [{}]}, [1], time_limit_ms=7000,
                include_all=True, runner_context=context,
            ), plan)
            self.assertTrue(any(call.kwargs.get("executable") == executable for call in runner.call_args_list))
            self.assertFalse(any(call.kwargs.get("executable") == Path("http.exe") for call in runner.call_args_list))
            custom_call = next(call for call in runner.call_args_list
                               if call.kwargs.get("executable") == executable)
            self.assertEqual(custom_call.args[0]["search"]["timeLimitMs"], 7000)
            self.assertTrue(custom_call.kwargs["return_response"])
            self.assertIn("candidate", context["pending_planner_state"])
            runner.reset_mock()
            gui.solve_auto_race({}, {}, [1], include_all=False)
            runner.assert_not_called()

    def test_auto_race_all_adapts_legacy_runner_budget_and_history(self):
        v1 = Path("v1.exe")
        h08 = Path("h08.exe")
        plan = [[-20]]
        seen = {v1: [], h08: []}

        def run(payload, timeout, executable=None, return_response=False):
            if executable in seen:
                seen[executable].append(json.loads(json.dumps(payload)))
            if executable == v1 and payload["search"]["timeLimitMs"] > 50000:
                raise RuntimeError("Runner exit code 1: timeLimitMs must be 1..50000")
            if executable == h08 and "history" in payload:
                raise RuntimeError("Runner exit code 1: self-traffic history cannot replay: agent 5 lacks fuel")
            return {"ok": True, "plan": plan}

        context = gui.new_runner_context()
        context["history"]["submitted_actions"] = [plan]
        with patch.dict(gui.CUSTOM_RUNNERS, {"EXE: v1": v1, "EXE: h08": h08}, clear=True), \
             patch.object(gui, "normalize_map_config"), \
             patch.object(gui, "run_runner", side_effect=run), \
             patch.object(gui, "check_plan_score", return_value={"valid": True, "servings": 1}), \
             patch.object(gui.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "native failed")):
            self.assertEqual(gui.solve_auto_race(
                {}, {"agents": [{}]}, [1], time_limit_ms=60000,
                include_all=True, runner_context=context,
            ), plan)

        self.assertEqual([item["search"]["timeLimitMs"] for item in seen[v1]], [60000, 50000])
        self.assertIn("history", seen[h08][0])
        self.assertNotIn("history", seen[h08][1])

    def test_v2_payload_carries_budget_history_and_planner_state(self):
        context = gui.new_runner_context()
        context["planner_state"] = {"policy": "chokudai_v2", "suffix": []}
        config = {
            "map": {"width": 1, "height": 1, "cells": [[0]]},
            "agents": [0], "spots": [{"pos": 0, "brand": 7, "stocks": 1}],
        }
        payload = gui.build_procon26_payload(
            config, {"agents": [{"kind": 0, "pos": 0, "fuel": 1}], "steps": 3},
            1, {}, context, 70000,
        )
        self.assertIs(payload["history"], context["history"])
        self.assertEqual(payload["planner_state"], context["planner_state"])
        self.assertEqual(payload["search"]["timeLimitMs"], 60000)
        self.assertEqual(payload["search"]["randomSeed"], 1)

    def test_v2_context_commits_only_accepted_day_data(self):
        context = gui.new_runner_context()
        plan = [[-3]]
        config = {"spots": [{"brand": 2}, {"brand": 5}, {"brand": 5}]}
        gui.commit_runner_day(context, config, plan, {"suffix": [plan]}, 9)
        self.assertEqual(context["history"], {
            "distinct_brands": [2, 5],
            "submitted_actions": [plan],
            "cumulative_daily_types": 2,
            "total_servings": 9,
        })
        self.assertEqual(context["planner_state"], {"suffix": [plan]})

    def test_runner_day_never_advances_from_local_history(self):
        context = gui.new_runner_context()
        context["history"]["submitted_actions"] = [[[1]], [[2]], [[3]]]
        self.assertEqual(gui.read_server_day({"current_day": "4"}), 4)
        self.assertEqual(gui.resume_runner_day({}, context), 1)
        self.assertEqual(gui.resume_runner_day({"currentDay": 1}, context), 1)
        self.assertEqual(gui.resume_runner_day({"current_day": 4}, context), 4)
        config = {"daySteps": [1] * 5, "spots": [{"brand": i} for i in range(13)]}
        self.assertEqual(gui.infer_server_day(
            {"currentDay": 1, "score": {"total_udon_daily_types": 39}}, config), 4)

    def test_runner_recovery_builds_neutral_past_days(self):
        config = {
            "agents": [4, 8], "daySteps": [10, 20, 30],
            "spots": [{"brand": 2}, {"brand": 5}],
        }
        context = gui.recover_runner_context(config, 3)
        self.assertTrue(context["recovered"])
        self.assertEqual(context["history"]["submitted_actions"], [
            [[-11], [-11]], [[-21], [-21]],
        ])
        self.assertEqual(context["history"]["distinct_brands"], [2, 5])
        self.assertEqual(context["history"]["cumulative_daily_types"], 4)
        self.assertEqual(context["history"]["total_servings"], 0)

    def test_resubmission_replaces_pending_and_commits_on_day_advance(self):
        config = {"agents": [0], "daySteps": [3, 3],
                  "spots": [{"brand": 1}, {"brand": 2}]}
        context = gui.new_runner_context()
        gui.stage_runner_day(context, 1, [[-3]], {"revision": 1}, 4)
        gui.stage_runner_day(context, 1, [[1, -2]], {"revision": 2}, 5)
        self.assertEqual(context["history"]["submitted_actions"], [])
        gui.reconcile_runner_context(context, config, 2)
        self.assertEqual(context["history"]["submitted_actions"], [[[1, -2]]])
        self.assertEqual(context["history"]["total_servings"], 5)
        self.assertIsNone(context["pending"])

    def test_reconcile_trims_revision_polluted_history(self):
        config = {"agents": [0], "daySteps": [3] * 5,
                  "spots": [{"brand": 1}]}
        context = gui.new_runner_context()
        context["history"]["submitted_actions"] = [[[1]]] * 5
        context["servings_by_day"] = [1] * 5
        events = gui.reconcile_runner_context(context, config, 1)
        self.assertEqual(context["history"]["submitted_actions"], [])
        self.assertEqual(context["history"]["total_servings"], 0)
        self.assertTrue(any("trimmed" in event for event in events))

    def test_solve_plan_preserves_runner_planner_state(self):
        context = gui.new_runner_context()
        response = {"ok": True, "plan": [[-3]], "planner_state": {"suffix": []}}
        with patch.dict(gui.CUSTOM_RUNNERS, {"EXE: V2": Path("v2.exe")}, clear=True), \
             patch.object(gui, "normalize_map_config"), \
             patch.object(gui, "run_runner", return_value=response) as runner:
            plan = gui.solve_plan("EXE: V2", {"agents": [0]},
                                  {"agents": [{"kind": 0}], "steps": 3}, [0],
                                  time_limit_ms=59000, runner_context=context)
        self.assertEqual(plan, [[-3]])
        self.assertEqual(context["pending_planner_state"], {"suffix": []})
        self.assertTrue(runner.call_args.kwargs["return_response"])
        self.assertEqual(runner.call_args.args[0]["search"]["timeLimitMs"], 59000)

    def test_runner_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "solver with spaces.exe"
            executable.touch()
            roles_payload = {"op": "roles", "config": {"agents": [0, 1]}}
            plan_payload = {"op": "plan", "config": {}, "state": {"agents": [{}, {}]}}
            with patch.object(gui, "PROCON26_RUNNER", executable), patch.object(gui.subprocess, "run") as run:
                for payload, response, expected in [
                    (roles_payload, {"ok": True, "roles": [1, 0]}, [1, 0]),
                    (plan_payload, {"ok": True, "plan": [[-20], [-20]]}, [[-20], [-20]]),
                ]:
                    run.return_value = subprocess.CompletedProcess([], 0, json.dumps(response), "")
                    self.assertEqual(gui.run_runner(payload, 3), expected)
                    self.assertEqual(run.call_args.args[0], [str(executable.resolve())])
                    self.assertEqual(run.call_args.kwargs["cwd"], executable.parent.resolve())
                    self.assertEqual(json.loads(run.call_args.kwargs["input"]), payload)
                    self.assertEqual(run.call_args.kwargs["timeout"], 3)

                for payload, output in [
                    (roles_payload, 'log\n{"ok":true,"roles":[1,0]}'),
                    (roles_payload, '[]'),
                    (roles_payload, '{"ok":false,"error":"failed"}'),
                    (roles_payload, '{"ok":true,"roles":[1]}'),
                    (roles_payload, '{"ok":true,"roles":[true,0]}'),
                    (roles_payload, '{"ok":true,"roles":[2,0]}'),
                    (plan_payload, '{"ok":true,"plan":[["bad"],[]]}'),
                    (plan_payload, '{"ok":true,"plan":[true,[]]}'),
                ]:
                    with self.subTest(output=output):
                        run.return_value = subprocess.CompletedProcess([], 0, output, "")
                        with self.assertRaises(RuntimeError):
                            gui.run_runner(payload, 3)

                run.return_value = subprocess.CompletedProcess([], 1, "", "missing DLL")
                with self.assertRaisesRegex(RuntimeError, "missing DLL"):
                    gui.run_runner(roles_payload, 3)
                run.return_value = subprocess.CompletedProcess(
                    [], 1, '{"ok":false,"error":"history/day mismatch"}', "")
                with self.assertRaisesRegex(RuntimeError, "history/day mismatch"):
                    gui.run_runner(roles_payload, 3)
                for error in [OSError("cannot launch"), subprocess.TimeoutExpired("runner", 3)]:
                    run.side_effect = error
                    with self.assertRaises(RuntimeError):
                        gui.run_runner(roles_payload, 3)
                run.reset_mock()
                executable.unlink()
                with self.assertRaisesRegex(RuntimeError, "not found"):
                    gui.run_runner(roles_payload, 3)
                run.assert_not_called()


class RoleSelectionTests(unittest.TestCase):
    def config(self):
        return {"startsAt": 0, "daySeconds": [30], "daySteps": [2],
                "map": {"width": 8, "height": 8, "cells": [[0] * 8 for _ in range(8)]},
                "agents": [0, 56, 63], "spots": [
                    {"pos": 1, "brand": 0, "stocks": 1},
                    {"pos": 48, "brand": 1, "stocks": 1},
                    {"pos": 62, "brand": 2, "stocks": 1}],
                "fuelLimits": 1000, "players": 1, "busyThreshold": 2, "jammedThreshold": 4}

    def test_masks_are_not_forced_to_include_refuel(self):
        self.assertEqual(gui.validate_roles([0, 0, 0], 3), [0, 0, 0])
        for roles in ([True, 0, 0], [2, 0, 0], [0, 0], []):
            with self.assertRaises(ValueError):
                gui.validate_roles(roles, 3)

    def test_native_all_patrol_keeps_three_brands(self):
        config = self.config()
        roles = gui.solve_roles("alns", config)
        self.assertEqual(roles, [0, 0, 0])
        scores = []
        for candidate in (roles, [1, 0, 0]):
            day = {"day": 0, "steps": 2, "endsAt": 100,
                   "agents": [{"pos": pos, "kind": role, "fuel": 1000 if role == 0 else 0}
                              for pos, role in zip(config["agents"], candidate)],
                   "others": [], "traffics": []}
            payload = {"config": config, "day_info": day, "types": candidate,
                       "search": {"timeLimitMs": 100, "minIterations": 0, "maxIterations": 12}}
            result = subprocess.run([str(gui.HEX_BINARY), "plan", "alns"],
                                    input=json.dumps(payload), capture_output=True, text=True,
                                    timeout=5, check=True)
            actions = json.loads(result.stdout)
            score = gui.check_plan_score(config, day, actions)
            self.assertTrue(score["valid"])
            scores.append(score["distinct_types"])
        self.assertEqual(scores, [3, 2])

    def test_cancel_and_missing_config_do_not_launch_selector(self):
        with patch.object(gui.subprocess, "Popen") as launch:
            with self.assertRaises(RuntimeError):
                gui.solve_roles("alns", self.config(), lambda: True)
            with self.assertRaises(ValueError):
                gui.solve_roles("alns", {})
            launch.assert_not_called()

    def test_timeout_keeps_complete_incumbent(self):
        process = Mock(returncode=1)
        process.communicate.side_effect = [subprocess.TimeoutExpired("select", 0.05),
                                          ('{"types":[0,0,0],"phase":"screen"}\n{"types":', '')]
        with patch.object(gui.subprocess, "Popen") as launch, patch.object(gui.time, "monotonic", side_effect=[0, 10]):
            launch.return_value.__enter__.return_value = process
            self.assertEqual(gui.solve_roles("alns", self.config()), [0, 0, 0])
            process.kill.assert_called_once()

    def test_selector_failure_is_not_silently_replaced(self):
        process = Mock(returncode=2)
        process.communicate.return_value = ('{"types":[0,0,0]}', 'bad config')
        with patch.object(gui.subprocess, "Popen") as launch:
            launch.return_value.__enter__.return_value = process
            with self.assertRaisesRegex(RuntimeError, "exited 2"):
                gui.solve_roles("alns", self.config())

    def test_http_auto_submit_does_not_use_displayed_roles(self):
        app = Mock(is_running=False, role_mode="auto")
        app.cbo_solver.get.return_value = "HTTP: Test"
        with patch.dict(gui.SOLVERS, {"HTTP: Test": "HTTP: Test"}):
            gui.HexControlCenter.submit_roles_now(app)
        app.api.submit_roles.assert_not_called()
        app.get_selected_roles.assert_not_called()

    def test_selector_distinguishes_ample_and_constrained_fuel(self):
        cells = [[1] * 16 for _ in range(16)]
        for pos in [0, 120, 240, 10, 50, 90, 130, 170, 210]:
            cells[pos // 16][pos % 16] = 0
        config = {
            "startsAt": 0, "daySeconds": [30, 30, 30, 30, 30], "daySteps": [33, 50, 66, 83, 99],
            "map": {"width": 16, "height": 16, "cells": cells},
            "agents": [0, 120, 240],
            "spots": [
                {"pos": 10, "brand": 0, "stocks": 2},
                {"pos": 50, "brand": 1, "stocks": 2},
                {"pos": 90, "brand": 2, "stocks": 2},
                {"pos": 130, "brand": 3, "stocks": 2},
                {"pos": 170, "brand": 0, "stocks": 2},
                {"pos": 210, "brand": 1, "stocks": 2},
            ],
            "fuelLimits": 69, "players": 1, "busyThreshold": 2, "jammedThreshold": 4,
        }
        # Constrained fuel across 5 days (331 steps vs 69 fuel) requires a refueler to keep scoring.
        roles_constrained = gui.solve_roles("alns", config)
        self.assertEqual(roles_constrained.count(1), 1)
        # Ample fuel (500 fuel) allows all patrol cars to avoid wasting a car on refueling.
        config["fuelLimits"] = 500
        roles_ample = gui.solve_roles("alns", config)
        self.assertEqual(roles_ample, [0, 0, 0])

    def test_server_roles_take_precedence_without_resubmission(self):
        api = Mock()
        api.get_game_status.return_value = {"agents": [{"kind": 0}, {"kind": 1}, {"kind": 0}]}
        with patch.object(gui, "solve_roles") as solve:
            actual = gui.reconcile_roles(api, "match", "token", self.config(), "alns", None, lambda: False, Mock())
            self.assertEqual(actual, [0, 1, 0])
            solve.assert_not_called()
            api.submit_roles.assert_not_called()

    def test_failed_submission_never_continues_with_unconfirmed_roles(self):
        api = Mock()
        api.get_game_status.return_value = {"agents": []}
        api.submit_roles.side_effect = OSError("denied")
        with self.assertRaises(OSError):
            gui.reconcile_roles(api, "match", "token", self.config(), "alns", [0, 0, 0], lambda: False, Mock())

    def test_conflict_uses_actual_mask(self):
        api = Mock()
        api.get_game_status.side_effect = [{"agents": []}, {"agents": [{"kind": 0}, {"kind": 1}, {"kind": 0}]}]
        api.submit_roles.side_effect = OSError("conflict")
        actual = gui.reconcile_roles(api, "match", "token", self.config(), "alns", [1, 0, 0], lambda: False, Mock())
        self.assertEqual(actual, [0, 1, 0])

    def test_delayed_confirmation_only_submits_once(self):
        api = Mock()
        api.get_game_status.side_effect = [
            {"agents": []}, {"agents": []}, OSError("temporary"),
            {"agents": [{"kind": 0}, {"kind": 0}, {"kind": 0}]}]
        log = Mock()
        with patch.object(gui.time, "sleep"):
            actual = gui.reconcile_roles(api, "match", "token", self.config(), "alns", [0, 0, 0], lambda: False, log)
        self.assertEqual(actual, [0, 0, 0])
        api.submit_roles.assert_called_once()
        self.assertIn("CHỜ XÁC NHẬN", str(log.call_args_list))
        self.assertEqual(log.call_args.args[1], "SUCCESS")

    def test_confirmation_timeout_does_not_claim_rejection_or_resubmit(self):
        api = Mock()
        api.get_game_status.return_value = {"agents": []}
        log = Mock()
        with self.assertRaisesRegex(TimeoutError, "Không đồng nghĩa bị từ chối"):
            gui.reconcile_roles(api, "match", "token", self.config(), "alns", [0, 0, 0], lambda: False, log, confirmation_timeout=0)
        api.submit_roles.assert_called_once()
        self.assertFalse(any(call.args[1] == "SUCCESS" for call in log.call_args_list))

    def test_cancel_while_waiting_never_resubmits(self):
        api = Mock()
        api.get_game_status.return_value = {"agents": []}
        cancelled = Mock(side_effect=[False, False, True])
        with patch.object(gui.time, "sleep"), self.assertRaisesRegex(RuntimeError, "Đã dừng chờ"):
            gui.reconcile_roles(api, "match", "token", self.config(), "alns", [0, 0, 0], cancelled, Mock())
        api.submit_roles.assert_called_once()

    def test_submit_empty_http_success_and_explicit_failure(self):
        api = gui.HauiAPI("https://example.test")
        response = Mock(status=204)
        response.read.return_value = b""
        log = Mock()
        with patch.object(gui.urllib.request, "urlopen") as request:
            request.return_value.__enter__.return_value = response
            self.assertEqual(api.submit_roles("match", "secret", [0, 0, 0], log_fn=log), {})
            self.assertIn("HTTP 204", log.call_args.args[0])
            response.status = 200
            response.read.return_value = b'{"ok": false}'
            with self.assertRaises(RuntimeError):
                api.submit_roles("match", "secret", [0, 0, 0], log_fn=log)

    def test_auto_ui_preserves_mode_without_eager_solver_or_cached_map(self):
        app = gui.HexControlCenter()
        app.withdraw()
        try:
            with patch.object(gui, "solve_roles") as solve:
                app.cbo_role_preset.current(2)
                app.on_role_preset_changed()
                app.update_agent_role_ui(3)
                self.assertEqual(app.role_mode, "auto")
                self.assertEqual(app.cbo_role_preset.current(), 2)
                app.update_agent_role_ui(4)
                self.assertEqual(app.role_mode, "auto")
                self.assertEqual(app.cbo_role_preset.current(), 2)
                solve.assert_not_called()
            app.is_running = True
            app.http_process = None
            with patch.object(app.api, "submit_roles") as submit:
                app.submit_roles_now()
                submit.assert_not_called()
            app.is_running = False
            for combo in app.agent_role_combos:
                combo.current(0)
            app.on_agent_role_changed()
            self.assertEqual(app.role_mode, "manual")
            self.assertEqual(app.get_selected_roles(), [0, 0, 0, 0])
        finally:
            for callback in app.tk.splitlist(app.tk.call("after", "info")):
                app.after_cancel(callback)
            app.destroy()

if __name__ == "__main__":
    unittest.main()
