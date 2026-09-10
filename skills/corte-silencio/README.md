# corte-silencio

Corta as pausas de um vídeo de fala e normaliza o áudio. No modo padrão roda **offline e de graça**: só `auto-editor` e `ffmpeg`, nenhuma API, nenhum upload.

Com a flag `--vicios`, também tira "né", "tá", "tipo" parasita e gagueira, usando transcrição com timestamp por palavra. Esse modo custa centavos de API e **é só para português brasileiro**.

## Instalação

Dentro do Claude Code (não precisa de Node):

```
/plugin marketplace add AndersonAdelino/skills
/plugin install adelino-skills@adelino
```

Ou, se quiser os arquivos editáveis dentro do seu projeto: `npx skills add AndersonAdelino/skills`.
Ou copie a pasta `corte-silencio/` para `.claude/skills/` no seu projeto (ou `~/.claude/skills/` para todos).

### Dependências

**É aqui que a maioria trava, não na instalação da skill.** São duas coisas: os pacotes Python e o `ffmpeg`.

```bash
pip install -r requirements.txt
```

E o `ffmpeg` (com `ffprobe`) no PATH:

| Sistema | Comando |
|---|---|
| Windows | `winget install Gyan.FFmpeg` |
| macOS | `brew install ffmpeg` |
| Linux (Debian/Ubuntu) | `sudo apt install ffmpeg` |

Confira que ficou tudo de pé:

```bash
auto-editor --version && ffmpeg-normalize --version && ffmpeg -version
```

Os três precisam responder com um número de versão. Se algum reclamar:

| Erro | O que fazer |
|---|---|
| `ffmpeg não é reconhecido` / `command not found` | O `ffmpeg` foi instalado mas não entrou no PATH. **Feche e abra o terminal** — resolve na maioria das vezes. Se persistir, adicione a pasta `bin` do ffmpeg ao PATH na mão |
| `pip não é reconhecido` | Python não está instalado ou ficou fora do PATH. Reinstale de [python.org](https://www.python.org/downloads/) marcando **"Add Python to PATH"** |
| `auto-editor não é reconhecido` (mas o pip install funcionou) | A pasta de scripts do pip está fora do PATH. Contorne rodando `python -m auto_editor` no lugar de `auto-editor` |

### Só para o modo `--vicios`

Precisa de uma chave da [OpenRouter](https://openrouter.ai/keys) em `OPENROUTER_API_KEY`. O jeito mais seguro é variável de ambiente, porque não cria arquivo nenhum para vazar:

```powershell
# Windows (PowerShell) — vale só para esta janela do terminal
$env:OPENROUTER_API_KEY = "sk-or-..."
```

```bash
# macOS / Linux
export OPENROUTER_API_KEY="sk-or-..."
```

Para não redigitar a cada sessão, use `.env` — mas leia o aviso abaixo:

```bash
cp .env.example .env
# abra o .env e preencha a chave
```

O script procura a chave no ambiente primeiro; se não achar, varre `.env` subindo as pastas a partir dele. Ele lê **só** `OPENROUTER_API_KEY` — nenhuma outra variável do seu `.env` entra no processo. Sem chave, para com uma mensagem explicando, não quebra no meio.

> ⚠️ **Se você usar `.env`, confirme que ele está no `.gitignore` do seu projeto.** O `.gitignore` deste repositório bloqueia `.env`, mas quando você instala a skill dentro de outro projeto, quem manda é o `.gitignore` de lá. Um `.env` em `.claude/skills/corte-silencio/` vai para o commit se o seu projeto não tiver a regra `.env`.

## Uso

Fale com o Claude naturalmente:

> corta os silêncios do `C:/videos/aula-03.mp4`

> tira as pausas e os "né" desse vídeo aqui: `~/gravacoes/live.mp4` --vicios

Ou chame direto: `/corte-silencio <caminho-do-video> [--vicios]`

## Onde o vídeo é salvo

Numa subpasta `editado/` **ao lado do seu vídeo**. A skill não tem pasta própria e não escreve em lugar nenhum do sistema: onde está a entrada, ali sai a saída.

```
C:\Users\joao\Downloads\
├── live.mp4                    ← seu arquivo, intocado
└── editado\
    └── live_editado.mp4        ← o resultado
```

Vale igual no macOS e no Linux: `~/videos/aula.mp4` vira `~/videos/editado/aula_editado.mp4`.

Três garantias que a skill leva a sério:

- **O original nunca é sobrescrito.** A saída sempre tem nome e pasta diferentes
- Durante o processamento aparece um `editado/_tmp/` com o arquivo intermediário. Ele é **apagado no fim**, inclusive a pasta
- Se você quiser outro destino, é só dizer: "salva em `D:/prontos`" e ele usa o seu

## O que sai do outro lado

- Silêncios e pausas removidos (`--edit audio:threshold=4%`, com respiro de `0.2s` nas pontas)
- Áudio normalizado em **-16 LUFS** com teto de pico em **-1,5 dBTP**, por loudness EBU R128 **linear** — sobe áudio baixo sem estourar e **sem compressor**, então a dinâmica da voz continua intacta
- Vídeo sem reencode na etapa de normalização (`-c:v copy`)

## Ajustes que valem a pena

| Situação | O que mudar |
|---|---|
| Aula, tutorial, vídeo longo | `--margin 0.2s` (padrão) |
| Anúncio, VSL, corte curto | `--margin 0.0s` — cada respiro preservado derruba o ritmo |
| Ficou apressado demais | Suba a margem para `0.3s` ou `0.4s` |
| Está comendo pausa natural | Baixe o threshold: `--edit "audio:threshold=2%"` |

## Como funciona o `--vicios`

1. **Analisa** — transcreve com `openai/whisper-large-v3-turbo` (timestamp por palavra), pega gagueira por heurística e submete o resto ao julgamento de um LLM
2. **Mostra a lista e espera seu OK** — nada é cortado sem aprovação. Cada corte aparece com timestamp e a frase em volta
3. **Aplica** — corte de silêncio e corte de vício saem no mesmo passe do `auto-editor`, com a normalização junto: um encode só

```bash
# 1. analisar (não corta nada)
python scripts/corte-vicios.py video.mp4 --json vicios.json

# 2. revisar a lista, editar o array "cortes" do JSON se quiser tirar algum

# 3. aplicar
python scripts/corte-vicios.py --aplicar video.mp4 vicios.json saida.mp4
# em anúncio, cole a fala:  --margin 0.0s
```

O script se recusa a fazer besteira sozinho:

- Aborta se o julgamento marcar mais de **15%** das palavras (isso não é vício, é o LLM tendo entendido errado)
- Recusa bloco de mais de **6 palavras seguidas**
- Protege vocativo (`pessoal`, `galera`, `gente`) e pronome (`eu`, `ele`, `você`) — tirar o sujeito quebra a frase
- Em gagueira, mantém a **última** repetição, que é a que emenda na frase

Autoteste das heurísticas, sem gastar API:

```bash
python scripts/corte-vicios.py --autoteste
```

## Limites conhecidos

- O julgamento de vício é **só PT-BR** — o prompt é escrito e calibrado em português brasileiro
- Whisper alucina "Obrigado" em trechos de silêncio no PT. Como esses cortes caem em cima de silêncio, que o `--edit` removeria de qualquer jeito, são inofensivos
- `--video-codec copy` / `--audio-codec copy` não existem no `auto-editor` 29.x (dão `Unknown encoder: copy`)
- Rodar dois `auto-editor` em paralelo sem `--temp-dir` separado corrompe a saída
- Cada vídeo precisa de ~2,3x o próprio tamanho livre em disco durante o processamento

## Testado com

`auto-editor` 29.3.1 · `ffmpeg-normalize` 1.42.0 · Python 3.12 · Windows 11

## Licença

MIT.
