#include "hexa_udon/session/session.hpp"
#include <cassert>
#include <deque>

class Transport final : public hexa_udon::protocol::HttpTransport {
public:
    std::deque<hexa_udon::protocol::Result<hexa_udon::protocol::HttpResponse>> responses;
    int calls = 0;
    hexa_udon::protocol::Result<hexa_udon::protocol::HttpResponse> execute(
        const hexa_udon::protocol::HttpRequest&) override {
        assert(!responses.empty());
        ++calls;
        auto result = std::move(responses.front());
        responses.pop_front();
        return result;
    }
};

int main() {
    using namespace hexa_udon;
    auto map = core::MapDefinition::create(8, 8, std::vector<core::Terrain>(64, core::Terrain::Plain));
    assert(map);
    core::MatchConfig config{0, {60}, {40}, std::move(map.value()), {}, {{0}}, 20, 1, 1, 2};
    const core::DailyState day{60, 0, {{core::AgentKind::Patrol, {0}, 20}}, {}, {}};
    protocol::ApiConfig api_config;
    api_config.base_url = "http://example.invalid";
    api_config.minimum_request_interval = std::chrono::milliseconds{0};
    for (const auto code : {protocol::ErrorCode::ConnectionTimeout, protocol::ErrorCode::TransferTimeout}) {
        Transport transport;
        transport.responses.push_back(protocol::Result<protocol::HttpResponse>::failure({code, "curl=28"}));
        transport.responses.push_back(protocol::Result<protocol::HttpResponse>::success(
            {200, R"({"revision":1})", std::chrono::milliseconds{1}}));
        protocol::ProconApiClient api(transport, api_config);
        session::SessionController controller(api, config);
        assert(controller.observe_day(day));
        const auto first = controller.submit_safe_wait(false);
        assert(!first);
        assert(controller.snapshot().submissions.size() == 1);
        if (code == protocol::ErrorCode::ConnectionTimeout) {
            assert(first.error().submission_attempted == false);
            assert(controller.state() != session::SessionState::RecoveryRequired);
            assert(controller.submit_safe_wait(false));
            assert(transport.calls == 2);
            assert(controller.snapshot().accepted_days.size() == 1);
        } else {
            assert(!first.error().submission_attempted.has_value());
            assert(controller.state() == session::SessionState::RecoveryRequired);
            assert(!controller.submit_safe_wait(false));
            assert(transport.calls == 1);
            assert(controller.snapshot().accepted_days.empty());
        }
    }
}
