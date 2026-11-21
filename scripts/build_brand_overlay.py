#!/usr/bin/env python3
"""Apply only public branding files to an existing compiled Postlane frontend."""
import argparse
import re
import shutil
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('existing_dist', type=Path)
p.add_argument('output_dist', type=Path)
a = p.parse_args()
source, output = a.existing_dist.resolve(), a.output_dist.resolve()
root = Path(__file__).resolve().parents[1]
if output.exists() or source == output or source in output.parents:
    p.error('Output must be a new directory outside the input frontend')
if not (source / 'index.html').is_file() or not (source / 'assets').is_dir():
    p.error('Input must be a compiled Postlane frontend')
if any(x.is_symlink() for x in source.rglob('*')):
    p.error('Refusing symlinks in the compiled frontend')
html = (source / 'index.html').read_text()
if 'Postlane' not in html or not re.search(r'/assets/[^\"]+\.js', html):
    p.error('Existing Postlane application entry point not found')
shutil.copytree(source, output)
html = re.sub(r'\s*<link\b(?=[^>]*\brel="(?:icon|apple-touch-icon)")[^>]*>', '', html)
links = '''    <link rel="icon" type="image/png" sizes="32x32" href="/branding/postlane-icon-32.png" />
    <link rel="apple-touch-icon" sizes="180x180" href="/branding/postlane-icon-180.png" />
    <link rel="stylesheet" href="/branding/postlane-brand-v1.css" />
'''
html = html.replace('</head>', links + '  </head>')
(output / 'index.html').write_text(html)
shutil.copytree(root / 'public/branding', output / 'branding')
for name in ['manifest.webmanifest', 'sw.js']:
    shutil.copy2(root / 'public' / name, output / name)
print('Branding overlay prepared; existing application bundles preserved.')
