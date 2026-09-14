"""Print display rectangles for an atlas without changing any bitmap pixels.

Usage: python3 previews/inspect_craft_atlas.py assets/craft/file.png 6 5
"""
from __future__ import annotations

import json
import sys
from PIL import Image


def display_bounds(path, columns, rows):
    image = Image.open(path).convert('RGB')
    width, height = image.size
    pixels = image.load()
    mask = [[max(pixels[x, y]) > 40 for x in range(width)] for y in range(height)]
    x_weights = [sum(row[x] for row in mask) for x in range(width)]
    y_weights = [sum(row) for row in mask]

    def cuts(weights, count):
        size = len(weights)
        result = [0]
        for index in range(1, count):
            expected = size * index / count
            radius = size / count * .2
            candidates = range(max(result[-1] + 1, int(expected - radius)), min(size, int(expected + radius)))
            # Choose empty gutters nearest the uniform grid. Tolerate a small
            # amount of dark pixel noise while retaining every bright detail.
            result.append(min(candidates, key=lambda x: (weights[x], abs(x - expected))))
        return result + [size]

    xs, ys = cuts(x_weights, columns), cuts(y_weights, rows)
    rects = []
    for row in range(rows):
        for column in range(columns):
            points = [(x, y) for y in range(ys[row], ys[row + 1])
                      for x in range(xs[column], xs[column + 1]) if mask[y][x]]
            if not points:
                raise ValueError('Empty sprite at row %s column %s' % (row + 1, column + 1))
            left, right = min(x for x, _ in points), max(x for x, _ in points)
            top, bottom = min(y for _, y in points), max(y for _, y in points)
            # Preserve a small black margin around the measured highlights.
            left, top = max(xs[column], left - 3), max(ys[row], top - 3)
            right, bottom = min(xs[column + 1] - 1, right + 3), min(ys[row + 1] - 1, bottom + 3)
            rects.append([left, top, right - left + 1, bottom - top + 1])
    return dict(width=width, height=height, rects=rects)


if __name__ == '__main__':
    print(json.dumps(display_bounds(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))))
