import argparse
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


def crawl_site(base_url: str) -> tuple[list[str], str]:
    base_url = base_url.rstrip('/')
    parsed = urlparse(base_url)
    base_root = f"{parsed.scheme}://{parsed.netloc}"

    start_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path or '/', '', '', ''))
    visited: set[str] = set()
    queue = deque([start_url])

    while queue:
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)
        try:
            response = requests.get(url)
            response.raise_for_status()
        except requests.RequestException:
            continue

        soup = BeautifulSoup(response.text, 'html.parser')
        for tag in soup.find_all('a', href=True):
            href = tag['href']
            abs_url = urljoin(url, href)
            parsed_href = urlparse(abs_url)
            if parsed_href.netloc != parsed.netloc:
                continue
            cleaned = urlunparse((parsed_href.scheme, parsed_href.netloc, parsed_href.path, '', '', ''))
            if cleaned not in visited:
                queue.append(cleaned)

    paths = sorted({urlparse(u).path.rstrip('/') or '/' for u in visited})
    return paths, base_root


def write_sitemap(base: str, paths: list[str], output: Path) -> None:
    import xml.etree.ElementTree as ET
    from xml.dom import minidom

    urlset = ET.Element('urlset', xmlns='http://www.sitemaps.org/schemas/sitemap/0.9')
    for path in paths:
        url_el = ET.SubElement(urlset, 'url')
        loc_el = ET.SubElement(url_el, 'loc')
        loc_el.text = urljoin(base + '/', path.lstrip('/'))

    xml_bytes = ET.tostring(urlset, encoding='utf-8')
    pretty = minidom.parseString(xml_bytes).toprettyxml(indent="  ")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(pretty, encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser(description='Generate sitemap.xml by crawling internal links.')
    parser.add_argument('--base-url', required=True, help='Base URL to crawl, e.g. https://example.com')
    args = parser.parse_args()

    paths, base = crawl_site(args.base_url)
    repo_root = Path(__file__).resolve().parents[1]
    output_path = repo_root / 'frontend' / 'public' / 'sitemap.xml'
    write_sitemap(base, paths, output_path)
    print(f'Wrote {len(paths)} paths to {output_path}')


if __name__ == '__main__':
    main()
