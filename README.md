# skills

Skills para Claude Code, testadas em produção no meu fluxo de criação de conteúdo (YouTube, Instagram, roteiro de vídeo).

[![skills.sh](https://skills.sh/b/AndersonAdelino/skills)](https://skills.sh/AndersonAdelino/skills)

## Instalar

Escolha **um** dos caminhos. Os dois entregam as mesmas skills.

### 1. Plugin do Claude Code — recomendado

Não precisa de Node nem de nada instalado antes. Dentro do Claude Code:

```
/plugin marketplace add AndersonAdelino/skills
/plugin install adelino-skills@adelino
```

As skills ficam disponíveis em todos os seus projetos e atualizam sozinhas.
São somente leitura: para editar, use o caminho 2.

### 2. skills.sh — se quiser editar as skills

Copia os arquivos para dentro do seu projeto, aí você mexe no que quiser.
Precisa de [Node](https://nodejs.org) instalado.

```bash
npx skills add AndersonAdelino/skills
```

### 3. Na mão

Copie a pasta da skill que te interessa para `.claude/skills/` no seu projeto,
ou `~/.claude/skills/` para deixar disponível em todos.

## Skills

| Skill | O que faz | Dependências |
|---|---|---|
| [corte-silencio](skills/corte-silencio/) | Corta as pausas de um vídeo de fala e normaliza o áudio em -16 LUFS. Roda offline e de graça. Com `--vicios`, também tira "né", "tá" e gagueira (PT-BR, custa centavos de API) | Python, `ffmpeg`, `auto-editor`, `ffmpeg-normalize` |

Cada skill tem seu próprio README com instalação, uso e limites conhecidos.

## Status

Repositório em construção. As skills estão sendo adaptadas do meu hub de produtividade pessoal e chegam aqui aos poucos, sem dado de canal ou caminho pessoal.

## Sobre

Feito por Anderson Adelino. Conteúdo sobre IA e automação no [YouTube](https://www.youtube.com/@oandersonadelino).

## Licença

MIT. Use, adapte, redistribua.
