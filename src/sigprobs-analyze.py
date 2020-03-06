#!/usr/bin/env python3
# coding: utf-8
# SPDX-License-Identifier: Apache-2.0


# Copyright 2020 AntiCompositeNumber

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#   http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import json


def main():
    infile = "/data/project/anticompositebot/www/static/sigprobs.jsonl"
    with open(infile) as f:
        fulldata = {}
        stats = {}
        for i, rawline in enumerate(f):
            line = json.loads(rawline)
            for error in line.get("errors"):
                stats[error] = stats.setdefault(error, 0) + 1
            fulldata[line.pop("username")] = line

        stats["total"] = i

    with open("/data/project/anticompositebot/www/static/sigprobs.json", "w") as f:
        json.dump({"1": stats, "2": fulldata}, f, sort_keys=True, indent=4)


if __name__ == "__main__":
    main()
