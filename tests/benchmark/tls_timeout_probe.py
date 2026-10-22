"""Loopback-only diagnostic: pre-send TLS timeout versus a POST whose acknowledgment is lost."""
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[2]
SOURCE = r"""
#include "hexa_udon/protocol/http_transport.hpp"
#include <iostream>
int main(int argc, char** argv) {
    if (argc != 3) return 2;
    using namespace hexa_udon::protocol;
    CurlHttpTransport transport;
    HttpRequest request{HttpMethod::Post, argv[1], {}, "[]"};
    request.connect_timeout = std::chrono::milliseconds{500};
    request.total_timeout = std::chrono::milliseconds{1200};
    const auto result = transport.execute(request);
    if (result) return 3;
    std::cout << static_cast<int>(result.error().code) << "\n"
              << result.error().message << "\n";
    return static_cast<int>(result.error().code) == std::stoi(argv[2]) ? 0 : 4;
}
"""


def main():
    captured = []
    release = threading.Event()
    environment = {key: value for key, value in os.environ.items() if 'proxy' not in key.lower()}
    with tempfile.TemporaryDirectory(prefix='hexa-tls-probe-') as temporary:
        source = Path(temporary) / 'probe.cpp'
        executable = Path(temporary) / 'probe'
        source.write_text(SOURCE)
        subprocess.run(['g++', '-std=c++17', '-I', str(ROOT / 'include'), str(source),
            str(ROOT / 'src/protocol/http_transport.cpp'), '-lcurl', '-o', str(executable)], check=True)
        for scheme, expected_code in (('https', 2), ('http', 3)):
            captured.clear()
            release.clear()
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0))
                listener.listen(1)
                listener.settimeout(5)

                def stall():
                    connection, _ = listener.accept()
                    with connection:
                        connection.settimeout(3)
                        data = connection.recv(16384)
                        if scheme == 'http':
                            while not data.endswith(b'[]'):
                                chunk = connection.recv(16384)
                                if not chunk:
                                    break
                                data += chunk
                        captured.append(data)
                        release.wait(5)

                worker = threading.Thread(target=stall)
                worker.start()
                try:
                    result = subprocess.run([str(executable),
                        f'{scheme}://127.0.0.1:{listener.getsockname()[1]}/', str(expected_code)],
                        env=environment, capture_output=True, text=True, timeout=5)
                finally:
                    release.set()
                    worker.join(timeout=6)
                assert captured
                if scheme == 'https':
                    assert captured[0][0] == 22 and b'POST ' not in captured[0]
                    assert 'requestStarted=false' in result.stdout
                else:
                    assert captured[0].startswith(b'POST ') and captured[0].endswith(b'[]')
                    assert 'requestStarted=true' in result.stdout
                assert result.returncode == 0, result.stdout + result.stderr
                print(json.dumps(dict(scheme=scheme, expected_code=expected_code,
                    status='PASS', diagnostic=result.stdout.strip())))


if __name__ == '__main__':
    main()
