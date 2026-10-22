#include "hexa_udon/protocol/api_client.hpp"
#include "hexa_udon/protocol/request_id_digest.hpp"

#include <cassert>
#include <algorithm>
#include <deque>
#include <iostream>
#include <stdexcept>

namespace {

class FakeTransport final : public hexa_udon::protocol::HttpTransport {
public:
    std::deque<hexa_udon::protocol::Result<hexa_udon::protocol::HttpResponse>> results;
    std::vector<hexa_udon::protocol::HttpRequest> requests;

    hexa_udon::protocol::Result<hexa_udon::protocol::HttpResponse> execute(
        const hexa_udon::protocol::HttpRequest& request) override {
        assert(!results.empty());
        requests.push_back(request);
        auto result = std::move(results.front());
        results.pop_front();
        return result;
    }
};

hexa_udon::protocol::Error post_kind_error(
    hexa_udon::protocol::Result<hexa_udon::protocol::HttpResponse> transport_result) {
    using namespace hexa_udon;
    FakeTransport transport;
    transport.results.push_back(std::move(transport_result));
    protocol::ApiConfig config;
    config.base_url = "http://example.invalid";
    config.minimum_request_interval = std::chrono::milliseconds{0};
    protocol::ProconApiClient client(transport, std::move(config));
    auto result = client.post_agent_kinds({core::AgentKind::Patrol});
    assert(!result);
    return result.error();
}

}  // namespace

void check_haui_protocol() {
    using namespace hexa_udon;
    const auto require = [](bool passed) {
        if (!passed) throw std::runtime_error("HAUI protocol regression");
    };
    FakeTransport transport;
    protocol::ApiConfig config;
    config.base_url = "https://example.invalid";
    config.token = "test/secret";
    config.haui_match_id = "match-42";
    config.minimum_request_interval = std::chrono::milliseconds{0};
    protocol::ProconApiClient client(transport, config);
    const auto response = [&transport](std::string body, long status = 200) {
        transport.results.push_back(protocol::Result<protocol::HttpResponse>::success(
            {status, std::move(body), std::chrono::milliseconds{1}}));
    };
    const nlohmann::json setting = {
        {"startsAt", 1}, {"daySeconds", {60}}, {"daySteps", {40}},
        {"map", {{"height", 8}, {"width", 8}, {"cells", std::vector<std::vector<int>>(8, std::vector<int>(8, 0))}}},
        {"spots", nlohmann::json::array()}, {"agents", {0}}, {"fuelLimits", 20},
        {"players", 2}, {"busyThreshold", 2}, {"jammedThreshold", 4}};
    response(setting.dump());
    const auto match = client.get_setting();
    require(match.has_value());
    response("{}");
    require(client.post_agent_kinds({core::AgentKind::Patrol}).has_value());
    response(R"({"endsAt":100,"day":0,"agents":[{"kind":0,"pos":0,"fuel":20}],"others":[],"traffics":[]})");
    require(client.get_state(match.value()).has_value());
    response(R"({"revision":3})");
    const simulator::DayActionPlan plan{{simulator::WaitAction{40}}};
    const auto revision = client.post_actions(plan);
    require(revision.has_value() && revision.value() == 3);
    const std::vector<std::string> endpoints{"config", "agents", "status", "answer"};
    for (std::size_t index = 0; index < endpoints.size(); ++index) {
        const auto& request = transport.requests.at(index);
        require(request.url == config.base_url + "/api/game/matches/match-42/" + endpoints[index]);
        require(std::find(request.headers.begin(), request.headers.end(), "x-api-token: test/secret") != request.headers.end());
        require(request.url.find("secret") == std::string::npos);
        require(request.method == (index % 2 == 0 ? protocol::HttpMethod::Get : protocol::HttpMethod::Post));
    }
    require(transport.requests.at(1).body == "[0]");
    require(transport.requests.at(3).body == "[[-40]]");
    response("{}");
    const auto unknown = client.post_actions(plan);
    require(!unknown && !unknown.error().submission_attempted.has_value());
    response("", 404);
    const auto missing = client.get_setting();
    require(!missing && missing.error().message == "HTTP 404");
    config.token = "secret\r\nx-injected: value";
    protocol::ProconApiClient invalid_token(transport, config);
    require(!invalid_token.get_setting());
    config.token = "secret";
    config.haui_match_id = "../another-match";
    protocol::ProconApiClient invalid_id(transport, config);
    require(!invalid_id.get_setting());
    require(transport.requests.size() == 6);
    config.haui_match_id.clear();
    config.token = "test/secret";
    protocol::ProconApiClient original(transport, config);
    response(setting.dump());
    require(original.get_setting().has_value());
    require(transport.requests.back().url == config.base_url + "/setting?token=test%2Fsecret");
}

int main() {
    check_haui_protocol();
    {
        using namespace hexa_udon;
        class Log final : public protocol::OperationLogger {
        public:
            std::vector<protocol::OperationLogEntry> entries;
            void write(const protocol::OperationLogEntry& entry) noexcept override {
                entries.push_back(entry);
            }
        } log;
        FakeTransport transport;
        protocol::ApiConfig config;
        config.base_url = "http://example.invalid";
        config.token = "private/token";
        config.minimum_request_interval = std::chrono::milliseconds{0};
        protocol::ProconApiClient client(transport, config, nullptr, &log);
        const simulator::DayActionPlan plan{{simulator::WaitAction{40}}};
        for (const auto code : {protocol::ErrorCode::ConnectionTimeout, protocol::ErrorCode::TransferTimeout}) {
            transport.results.push_back(protocol::Result<protocol::HttpResponse>::failure(
                {code, "curl=28 private/token private%2Ftoken"}));
            const auto result = client.post_actions(plan, std::nullopt, "daily-submit", 1);
            assert(!result);
            assert(result.error().submission_attempted.has_value() == (code == protocol::ErrorCode::ConnectionTimeout));
            assert(result.error().message.find("curl=28") != std::string::npos);
            assert(result.error().message.find("private") == std::string::npos);
            assert(log.entries.back().operation == "http-transport");
            assert(log.entries.back().stop_reason.find("private") == std::string::npos);
            assert(log.entries.back().stop_reason.find("curl=28") != std::string::npos);
        }
        assert(transport.requests.size() == 2);
    }
    using hexa_udon::protocol::request_id_digest;
    using hexa_udon::protocol::request_id_digest_or_missing;
    const nlohmann::json id = "request-α";
    const auto escaped_id = nlohmann::json::parse(R"("request-\u03b1")");
    assert(request_id_digest(id) == request_id_digest(escaped_id));
    assert(request_id_digest_or_missing(id) != "missing");
    assert(request_id_digest_or_missing(nlohmann::json(nullptr)) == "missing");
    assert(request_id_digest_or_missing(nlohmann::json::object()) == "missing");
    assert(request_id_digest(nlohmann::json("")) != std::nullopt);

    using hexa_udon::protocol::ErrorCode;
    using hexa_udon::protocol::HttpResponse;
    using hexa_udon::protocol::Result;
    for (const auto code : {ErrorCode::DnsFailure, ErrorCode::ConnectionRefused,
                            ErrorCode::ConnectionTimeout}) {
        const auto error = post_kind_error(Result<HttpResponse>::failure({code, "not connected"}));
        assert(error.submission_attempted == false);
    }
    for (const auto code : {ErrorCode::TransferTimeout, ErrorCode::Disconnected}) {
        const auto error = post_kind_error(Result<HttpResponse>::failure({code, "after send"}));
        assert(!error.submission_attempted.has_value());
        assert(error.code == ErrorCode::UnknownResponse);
    }
    for (const long status : {400L, 403L, 429L}) {
        const auto rejected = post_kind_error(Result<HttpResponse>::success(
            {status, "", std::chrono::milliseconds{1}, {{"retry-after", "2"}}}));
        assert(rejected.submission_attempted == false);
        assert(rejected.retry_after_ms == 2000);
    }
    const auto server_error = post_kind_error(Result<HttpResponse>::success(
        {500, "", std::chrono::milliseconds{1}}));
    assert(!server_error.submission_attempted.has_value());
    std::cout << "protocol_request_id_digest_tests: PASS\n";
}
