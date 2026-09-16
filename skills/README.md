# skills

Uma pasta por skill: `skills/<nome>/SKILL.md`.

| Skill | O que faz | Precisa de |
|---|---|---|
| [cut-silence](cut-silence/) | Corta silêncio e pausa de vídeo de talking head e normaliza o áudio em -14 LUFS. Com `--fillers`, tira também vício de linguagem, gagueira e take repetido | Python, `ffmpeg`, `auto-editor`, `ffmpeg-normalize` |
| [thread-carousel](thread-carousel/) | Carrossel de Instagram no estilo thread do Twitter, a partir de um tema. Pesquisa quando o assunto é factual, escreve a copy e entrega PNG 1080×1350 | Python, Chrome ou Edge. Opcional: kie.ai, Pexels |
| [local-site-lift](local-site-lift/) | Refaz site feio de comércio local. Confronta o negócio com o perfil do Google, decide a direção visual antes do código e afere o artesanato do resultado | Python, navegador. Opcional: Apify, Pexels, kie.ai, ffmpeg |
| [cpanel-deploy](cpanel-deploy/) | Publica qualquer pasta estática num cPanel e confere se o endereço no ar é mesmo a página nova | Python. Um token de API do cPanel |

As duas últimas se completam: a `local-site-lift` termina numa pasta `dist/`, a
`cpanel-deploy` publica. São separadas de propósito — quem só quer o site não
precisa de token, e o publicador serve qualquer pasta, venha de Hugo, Astro,
Vite ou da mão.

## Instalar

Tudo:

```bash
npx skills add AndersonAdelino/skills
```

Só as que você quer:

```bash
npx skills add AndersonAdelino/skills --skill local-site-lift,cpanel-deploy
```

`-g` instala global (`~/.claude/skills`) em vez de no projeto atual, e `-y`
pula as confirmações. Para ver o que existe sem instalar nada:

```bash
npx skills add AndersonAdelino/skills --list
```

## Como cada uma se sustenta

Todo script é **stdlib do Python**, sem `pip install`: a skill roda na máquina
de quem contratou o trabalho, e instalar dependência na hora é um jeito de
falhar.

Todo script tem `--autoteste`, que roda **sem rede e sem chave**, e está no CI.
Os números dentro deles não são teoria: saíram de bug real, e o comentário ao
lado diz qual. Leia [MISTAKES.md](../MISTAKES.md) antes de mexer em parâmetro,
heurística ou caminho de deploy.

`scripts/validar-skills.py`, na raiz, confere o que não aparece lendo diff:
frontmatter que o YAML aceita, e toda skill presente no `plugin.json`, no README
e no CI.
