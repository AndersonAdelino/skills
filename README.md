# skills

Claude Code skills, battle-tested in my own content production workflow (YouTube, Instagram, video scripting).

[![skills.sh](https://www.skills.sh/b/AndersonAdelino/skills)](https://www.skills.sh/AndersonAdelino/skills)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![YouTube](https://img.shields.io/badge/YouTube-Anderson%20Adelino%20%C2%B7%209.1K-FF0000?logo=youtube&logoColor=white)](https://www.youtube.com/@oandersonadelino?sub_confirmation=1)

## Install

Pick **one**. Both give you the same skills.

### 1. Claude Code plugin — recommended

No Node, nothing to install first. Inside Claude Code:

```
/plugin marketplace add AndersonAdelino/skills
/plugin install adelino-skills@adelino
```

The skills become available in every project and update themselves.
They're read-only: to edit them, use option 2.

### 2. skills.sh — if you want to edit the skills

Copies the files into your project so you can change whatever you want.
Requires [Node](https://nodejs.org).

```bash
npx skills add AndersonAdelino/skills
```

### 3. By hand

Copy the skill folder you want into `.claude/skills/` in your project,
or `~/.claude/skills/` to have it everywhere.

## Skills

| Skill | What it does | Dependencies |
|---|---|---|
| [cut-silence](skills/cut-silence/) | Cuts the pauses out of talking-head video and normalizes audio to -14 LUFS. Runs offline and free. With `--fillers`, also removes filler words, stutters and duplicate takes (costs cents of API to transcribe) | Python, `ffmpeg`, `auto-editor`, `ffmpeg-normalize` |

Each skill has its own README with installation, usage and known limits.

## Status

Work in progress. These skills are being adapted from my personal productivity hub and land here gradually, stripped of channel data and personal paths.

## About

Built by Anderson Adelino. Content about AI and automation on [YouTube](https://www.youtube.com/@oandersonadelino).

## License

MIT. Use it, adapt it, redistribute it.
