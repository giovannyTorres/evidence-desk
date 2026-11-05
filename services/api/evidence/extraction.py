"""Resource-bounded text extraction subprocess; never imports model clients or credentials."""
import base64
import io
import json
from pathlib import Path
import sys
from pypdf import PdfReader


def extract(filename: str, content: bytes) -> list[tuple[str, str]]:
    suffix = Path(filename).suffix.lower()
    if suffix == '.pdf':
        if not content.startswith(b'%PDF-'):
            raise ValueError('Invalid PDF signature')
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted or len(reader.pages) > 100:
            raise ValueError('PDF must be unencrypted and at most 100 pages')
        sections = [(f'Page {i+1}', page.extract_text() or '') for i, page in enumerate(reader.pages)]
    elif suffix in {'.txt', '.md'}:
        decoded = content.decode('utf-8')
        if '\x00' in decoded:
            raise ValueError('Binary content is not accepted')
        sections = []
        heading = 'Section 1'
        lines: list[str] = []
        for line in decoded.splitlines():
            if line.startswith('#'):
                if lines:
                    sections.append((heading, '\n'.join(lines)))
                heading, lines = line.lstrip('# ').strip()[:160], []
            else:
                lines.append(line)
        sections.append((heading, '\n'.join(lines)))
    else:
        raise ValueError('Only text PDF, UTF-8 TXT and Markdown are supported')
    result = [(loc, body[start:start+1200]) for loc, body in sections if body.strip()
              for start in range(0, len(body), 1000)]
    if not result:
        raise ValueError('No extractable text found; scanned PDFs need OCR outside this product')
    if len(result) > 400:
        raise ValueError('Document exceeds 400 text fragments')
    return result


if __name__ == '__main__':
    try:
        # Supported runtime is Linux containers. Process limits terminate pathological parsers.
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
        request = json.loads(sys.stdin.buffer.read(8 * 1024 * 1024))
        print(json.dumps(extract(request['filename'], base64.b64decode(request['data']))))
    except Exception:
        print(json.dumps({'error': 'Document could not be safely extracted; use an unencrypted text PDF, UTF-8 TXT or Markdown.'}))
        raise SystemExit(1)
