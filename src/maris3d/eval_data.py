# SPDX-License-Identifier: Apache-2.0
"""Read the exported benchmark (eval/benchmark/prompts.jsonl): one JSON object per line with id, level, prompt, check."""
import json


def load_benchmark(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]
