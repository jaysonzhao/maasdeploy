"""HTTP framing compatibility for the unchanged pinned vLLM example adapter."""
import importlib.util
import io
import json
from pathlib import Path


source = Path(__file__).with_name('vendor_structured_server.py')
spec = importlib.util.spec_from_file_location('vendor_structured_server', source)
upstream = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upstream)

MAX_BODY = 32 * 1024 * 1024


def read_chunked(stream):
    body = bytearray()
    while True:
        line = stream.readline(8193)
        if len(line) > 8192 or not line.endswith(b'\r\n'):
            raise ValueError('invalid chunk header')
        size = int(line.split(b';', 1)[0].strip(), 16)
        if size < 0 or len(body) + size > MAX_BODY:
            raise ValueError('request body exceeds 32 MiB')
        if size == 0:
            trailer_bytes = 0
            while True:
                trailer = stream.readline(8193)
                trailer_bytes += len(trailer)
                if not trailer.endswith(b'\r\n') or trailer_bytes > 65536:
                    raise ValueError('invalid chunk trailer')
                if trailer == b'\r\n':
                    return bytes(body)
        chunk = stream.read(size)
        if len(chunk) != size or stream.read(2) != b'\r\n':
            raise ValueError('truncated chunk')
        body.extend(chunk)


class MaaSHandler(upstream.Handler):
    def _read_request(self):
        transfer = self.headers.get('Transfer-Encoding', '').lower().strip()
        if not transfer:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 <= size <= MAX_BODY:
                raise ValueError('request body exceeds 32 MiB')
            return super()._read_request()
        if transfer != 'chunked':
            raise ValueError('unsupported Transfer-Encoding')
        raw = read_chunked(self.rfile)
        original = self.rfile
        old_length = self.headers.get('Content-Length')
        del self.headers['Content-Length']
        self.headers['Content-Length'] = str(len(raw))
        self.rfile = io.BytesIO(raw)
        try:
            return super()._read_request()
        finally:
            self.rfile = original
            del self.headers['Content-Length']
            if old_length is not None:
                self.headers['Content-Length'] = old_length

    def _json(self, code, body):
        # The pinned chat adapter reports prompt_tokens=0 despite retaining the
        # real prompt count in its structured diagnostics. Preserve that count
        # for MaaS usage accounting when the engine supplies it.
        if code == 200 and body.get('object') == 'chat.completion':
            decision = json.loads(body['choices'][0]['message']['content'])
            prompt_tokens = decision.get('diagnostics', {}).get('prompt_tokens')
            if isinstance(prompt_tokens, int) and prompt_tokens >= 0:
                body['usage']['prompt_tokens'] = prompt_tokens
                body['usage']['total_tokens'] = prompt_tokens + body['usage']['completion_tokens']
        return super()._json(code, body)


upstream.Handler = MaaSHandler
if __name__ == '__main__':
    upstream.main()
