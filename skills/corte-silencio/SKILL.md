---
name: corte-silencio
description: Corta silêncio de UM vídeo via auto-editor e normaliza o áudio (-16 LUFS). Com a flag `--vicios`, também remove vícios de linguagem e gagueiras usando transcrição por palavra. Gatilhos "corta os silêncios", "remove as pausas do vídeo", "tira os tempos mortos", "tira os né/tá do vídeo", "corta as gagueiras", "acelera esse vídeo tirando as pausas". NÃO usar para edição criativa (escolher takes, legenda queimada, color grade, overlays, cortar por conteúdo) — esta skill só remove silêncio e som parasita. Se o pedido for genérico tipo "edita meu vídeo", pergunte o que exatamente antes de acionar.
argument-hint: <caminho-do-video> [--vicios]
license: MIT
---

## O que esta skill faz

Corta automaticamente pausas e silêncios de vídeos de fala usando `auto-editor`, depois normaliza o volume do áudio com `ffmpeg-normalize`.

- **Custo:** R$ 0 no modo padrão — ferramentas 100% gratuitas, open source e offline
- **Qualidade:** mantém a qualidade original do vídeo (sem reencoding de vídeo na normalização, `-c:v copy`)
- **Áudio:** normalização de loudness EBU R128 linear (sem compressão de dinâmica, sem efeitos) — sobe áudio baixo e desce áudio alto até o mesmo nível percebido, sem nunca estourar o pico
- **Output:** salva o vídeo editado em `<SAIDA>/` (ver convenção abaixo), nunca sobrescreve o original

**Modo opcional `--vicios`:** também remove vícios de linguagem ("né", "tá", "tipo" parasita) e gagueiras. Custa centavos de API (OpenRouter) porque precisa transcrever, e **é só para português brasileiro** — o prompt de julgamento é escrito em PT-BR e calibrado nele. **Não roda sem o usuário pedir.** Ver "Passo 5b".

---

## Convenção de caminhos

Esta skill é portátil: funciona copiada para qualquer máquina, sem depender da estrutura de nenhum projeto.

| Marcador | Significa |
|---|---|
| `<SAIDA>` | `<pasta onde está o vídeo>/editado` — criada se não existir. **Nunca** a pasta do original. |
| `<PASTA-DESTA-SKILL>` | a pasta onde este `SKILL.md` está. O script fica em `<PASTA-DESTA-SKILL>/scripts/corte-vicios.py` |

Se o usuário pedir outro destino, use o dele. Em lote, mantenha todos os vídeos na mesma `<SAIDA>`.

**Shell.** Os comandos abaixo estão em sintaxe POSIX (bash/zsh). No Windows PowerShell os equivalentes são:

| POSIX | PowerShell |
|---|---|
| `test -f "$1"` | `Test-Path -PathType Leaf "$caminho"` |
| `rm -rf "<pasta>"` | `Remove-Item -Recurse -Force "<pasta>"` |
| `rm -f "<arquivo>"` | `Remove-Item -Force "<arquivo>"` |
| `df -h` | `Get-PSDrive -PSProvider FileSystem` |

Use a ferramenta de shell nativa do ambiente. As chamadas de `auto-editor`, `ffmpeg-normalize` e `ffprobe` são idênticas nos dois.

---

## Passos

### 1. Receber o arquivo

O caminho do vídeo vem como argumento: `$1`

Se nenhum argumento foi fornecido, pergunte:
> "Qual o caminho do vídeo que você quer editar?"

### 2. Verificar dependências

Rode no terminal:

```bash
python --version
auto-editor --version
ffmpeg -version
ffmpeg-normalize --version
```

Faltando algum pacote Python, instale:

```bash
pip install auto-editor ffmpeg-normalize
```

Se `ffmpeg` não estiver instalado, instruir conforme o sistema:

| Sistema | Comando |
|---|---|
| Windows | `winget install Gyan.FFmpeg` (ou baixar de https://ffmpeg.org/download.html e adicionar ao PATH) |
| macOS | `brew install ffmpeg` |
| Linux (Debian/Ubuntu) | `sudo apt install ffmpeg` |

**Só para o modo `--vicios`** (pule se o usuário não pediu): precisa de `pip install openai` e de uma chave da OpenRouter em `OPENROUTER_API_KEY`, como variável de ambiente ou num `.env`. O script procura a chave no ambiente primeiro e, se não achar, varre `.env` subindo as pastas a partir dele — lendo **só** `OPENROUTER_API_KEY`, nunca as outras variáveis do `.env` do usuário. Sem chave, ele para com mensagem explicando, não quebra.

Não prossiga sem as dependências.

### 3. Verificar o arquivo de entrada

Confirme que o arquivo existe antes de qualquer outra coisa:

```bash
test -f "$1" && echo "OK" || echo "ARQUIVO NÃO ENCONTRADO"
```

Se não existir, informe:
> "Arquivo não encontrado: `$1`. Verifique o caminho e tente novamente."

### 4. Definir nomes dos arquivos

- Extraia o nome base do arquivo sem extensão.
- Intermediário (corte, antes de normalizar): `<SAIDA>/_tmp/<nome-base>.<extensao>`
- Final: `<SAIDA>/<nome-base>_editado.<extensao>`
- Cache isolado do auto-editor: `<SAIDA>/_tmp/cache_<nome-base>/`

Exemplo: `C:/Videos/aulas/tutorial.mp4` → `C:/Videos/aulas/editado/tutorial_editado.mp4`

### 5. Executar o corte de silêncios

```bash
auto-editor "<caminho-do-video>" \
  --edit "audio:threshold=4%" \
  --margin "0.2s" \
  --temp-dir "<SAIDA>/_tmp/cache_<nome-base>" \
  -o "<SAIDA>/_tmp/<nome-base>.<extensao>" \
  --no-open
```

**Parâmetros explicados:**
- `--edit "audio:threshold=4%"` → considera silêncio o trecho abaixo de 4% do volume máximo
- `--margin` → respiro preservado antes e depois de cada fala (ver tabela abaixo)
- `--temp-dir` → cache exclusivo desse vídeo (ver guardrail de paralelismo abaixo)
- `--no-open` → não abre o arquivo automaticamente após exportar

**A margem muda conforme o tipo de vídeo.** Não use 0.2s para tudo:

| Tipo de vídeo | `--margin` | Por quê |
|---|---|---|
| Aula, tutorial, vídeo longo falado | `0.2s` | O respiro nas pontas deixa a fala natural e evita corte abrupto |
| **Criativo, anúncio, VSL, corte curto** | **`0.0s`** | Ritmo é tudo. Cada 0,2s preservado por fala soma e derruba o corte; anúncio pede fala colada |

Na dúvida entre os dois, pergunte se é peça de anúncio ou conteúdo longo. Se o usuário reclamar que ficou apressado, suba a margem; se reclamar que ficou arrastado, baixe.

Depois de rodar, apague a pasta de cache: `rm -rf "<SAIDA>/_tmp/cache_<nome-base>"`.

> **Nota:** As flags `--video-codec copy` e `--audio-codec copy` **não são suportadas** na versão 29.x do auto-editor (geram `Unknown encoder: copy`). Não tente usá-las. O auto-editor mantém qualidade próxima do original com seu codec padrão (h264+aac).

### 5b. Cortar vícios de linguagem (SÓ com `--vicios`)

**Pule este passo inteiro se o usuário não pediu.** Ele custa API e demora.

Este passo substitui os passos 5 e 6, porque o corte de vício entra na *mesma* chamada do auto-editor, junto com o corte de silêncio. Um encode só, sem perda por recodificar duas vezes.

**1) Analisar** (não corta nada, só descobre onde estão os vícios):

```bash
python "<PASTA-DESTA-SKILL>/scripts/corte-vicios.py" "<caminho-do-video-ORIGINAL>" --json "<saida>.json"
```

Use o vídeo **original**, nunca o já cortado: os timestamps precisam bater com a linha de tempo que o auto-editor vai receber.

O script transcreve com timestamp por palavra (`openai/whisper-large-v3-turbo` via OpenRouter), detecta gagueira por heurística, submete o resto ao julgamento de um LLM, e imprime cada corte com a frase em volta.

**2) Mostrar a lista ao usuário e ESPERAR o OK.** Não aplique sozinho. Mostre o relatório como o script imprimiu (timestamp, tipo, frase com a palavra entre colchetes) e pergunte se pode aplicar. Se ele quiser tirar alguns da lista, edite o array `cortes` do JSON antes de seguir.

**3) Aplicar.** Depois do OK, o próprio script corta e normaliza:

```bash
python "<PASTA-DESTA-SKILL>/scripts/corte-vicios.py" --aplicar "<video-ORIGINAL>" "<vicios>.json" "<saida>.mp4"
```

Em peça de anúncio, passe a margem junto, pelo mesmo critério da tabela do passo 5 (o padrão do `--aplicar` é `0.2s`):

```bash
python "<PASTA-DESTA-SKILL>/scripts/corte-vicios.py" --aplicar "<video>" "<vicios>.json" "<saida>.mp4" --margin 0.0s
```

**Não monte a chamada do `auto-editor` na mão para isso.** O `--cut-out` da versão 29.x aceita **uma faixa por ocorrência da flag**, apesar do `--help` anunciar `[START,STOP ...]`. Passar várias juntas faz ele tratar a última como arquivo de entrada e morrer com `Could not open input file: 432.42sec,432.96sec`. O jeito certo é repetir a flag (`--cut-out A,B --cut-out C,D ...`), que é o que o script faz.

Corte de silêncio e corte de vício saem no mesmo passe, e a normalização vem junto: um encode só.

**Guardrails que o script já aplica sozinho** (não precisa refazer, mas saiba que existem):
- Aborta se o julgamento marcar mais de 15% das palavras — isso não é vício, é o LLM tendo entendido errado
- Recusa bloco de mais de 6 palavras seguidas
- Protege vocativo (`pessoal`, `galera`, `gente`, `cara`) e pronome (`eu`, `ele`, `você`): quem grava fala com a audiência o tempo todo, e cortar o sujeito quebra a frase ("o que ele corrigiu" vira "o que corrigiu")
- Em gagueira, mantém a **última** repetição, que é a que emenda na frase

**Se o usuário reclamar que ficou picotado:** o problema quase sempre é volume de cortes, não a emenda. Rode de novo sem `--vicios` e compare.

### 6. Normalizar o áudio

Pule este passo se rodou o `5b` — o `--aplicar` já normalizou.

```bash
ffmpeg-normalize "<SAIDA>/_tmp/<nome-base>.<extensao>" \
  -o "<SAIDA>/<nome-base>_editado.<extensao>" \
  -c:a aac -b:a 192k \
  -t -16 -tp -1.5 \
  --auto-lower-loudness-target \
  --print-stats -f
```

**Parâmetros explicados:**
- `-t -16` → alvo de loudness integrado EBU R128: -16 LUFS (padrão pra voz/aula)
- `-tp -1.5` → teto de pico verdadeiro em -1,5 dBTP, nunca estoura mesmo subindo áudio baixo
- `--auto-lower-loudness-target` → garante normalização **linear** (ganho reto). Sem essa flag, um áudio que não alcança o alvo sem estourar o pico cai automaticamente pra normalização **dinâmica** (efeito parecido com compressor) — o que viola "sem compressão nem efeitos"
- `-c:a aac -b:a 192k` → reencoda só o áudio; vídeo é copiado (`-c:v copy` é o padrão da ferramenta, não precisa passar)
- `--print-stats` → registra no log quanto de ganho foi aplicado em cada vídeo

Depois de normalizar com sucesso, apague o intermediário e a pasta de scratch, para não deixar lixo na pasta do usuário:

```bash
rm -f "<SAIDA>/_tmp/<nome-base>.<extensao>"
rmdir "<SAIDA>/_tmp" 2>/dev/null || true   # só remove se estiver vazia
```

### 7. Rodar em background (vídeos longos)

Para vídeos acima de ~10 minutos, o processo pode levar bastante tempo. Rode em background e monitore o progresso:

```bash
tail -f "<output-file>" | grep -E --line-buffered "%|done|error|Error|Traceback"
```

### 8. Reportar resultado

Após concluir, informe:

```
✅ Vídeo editado com sucesso!

📁 Arquivo original: <caminho-original>
💾 Arquivo editado:  <SAIDA>/<nome-editado>

⏱️ Duração original:  X min Y seg
⏱️ Duração final:     X min Y seg
✂️  Tempo economizado: Z seg (N% do vídeo)
🔊 Áudio normalizado: -16 LUFS (pico máx. -1,5 dBTP)
```

Para obter as durações, use:

```bash
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "<arquivo>"
```

---

## Guardrails

- **Nunca sobrescrever o original** — a saída vai sempre para `<SAIDA>/`, jamais substitui o arquivo de entrada.
- **Não prosseguir sem dependências** — sem `ffmpeg`, `auto-editor` e `ffmpeg-normalize` instalados, a skill para e instrui o usuário.
- **Não inventar caminhos** — se o arquivo não for encontrado, para e pede o caminho correto.
- **Não rodar em lote sem confirmação** — se o usuário passar uma pasta ao invés de um arquivo, confirme antes de processar todos.
- **`--vicios` nunca roda sozinho** — o modo padrão é grátis e offline; o corte de vício gasta API. Só entra se o usuário pedir explicitamente. E mesmo pedido, a lista de cortes vai para aprovação antes de aplicar.
- **Corte de vício sempre a partir do vídeo original** — se você transcrever o vídeo já cortado e aplicar as faixas no original (ou vice-versa), os timestamps não batem e a skill corta pedaço de fala boa.
- **Nunca rodar duas instâncias do `auto-editor` ao mesmo tempo sem `--temp-dir` isolado por vídeo** — colisão de cache corrompe a saída (áudio/vídeo com dados inválidos, ou pior, mistura conteúdo de outro cache que sobrou no temp). Se for processar vários vídeos em paralelo, cada chamada precisa do seu próprio `--temp-dir`, apagado logo depois de usar.
- **Espaço em disco antes de lote grande** — cada vídeo precisa de ~2,3x o próprio tamanho livre em disco (intermediário do corte + arquivo final coexistindo). Cheque o espaço livre antes de processar vários vídeos grandes; se não couber, pause e peça pro usuário liberar espaço em vez de deixar o ffmpeg falhar no meio.

---

## Troubleshooting

| Problema | Solução |
|---|---|
| `auto-editor: command not found` | `pip install auto-editor` |
| `ffmpeg-normalize: command not found` | `pip install ffmpeg-normalize` |
| `ffmpeg: command not found` | Instalar ffmpeg e adicionar ao PATH (ver tabela do passo 2) |
| Erro com `--video-codec copy` | Não usar — flag não existe na versão 29.x do auto-editor |
| Vídeo com áudio dessincronizado | Não use `copy` em vídeos com múltiplas faixas de áudio |
| Cortes muito agressivos / ficou apressado | Aumentar `--margin` para `0.3s` ou `0.4s` |
| Criativo ficou arrastado, com respiro sobrando | Baixar `--margin` para `0.0s` — é o padrão para anúncio |
| Pausas naturais sendo cortadas | Baixar o threshold: `--edit "audio:threshold=2%"`. Quanto menor o threshold, menos coisa conta como silêncio. (A flag `--silent-threshold` foi removida do auto-editor; não existe mais na 29.x) |
| `Invalid NAL unit size` / `Found duplicated MOOV Atom` / erro de decodificação na normalização | Cache do `auto-editor` colidiu com outra instância rodando ao mesmo tempo. Apague o `--temp-dir` daquele vídeo, rode de novo sozinho (sem paralelismo) ou com `--temp-dir` exclusivo |
| `--vicios`: `OPENROUTER_API_KEY nao encontrada` | Defina a variável de ambiente ou copie o `.env.example` da skill para `.env` e preencha a chave |
| `--vicios`: `ABORTADO: marcou N% das palavras` | O LLM entendeu a tarefa errado. Rode de novo; se repetir, o áudio provavelmente tem ruído/música confundindo a transcrição |
| `--vicios`: `transcricao voltou sem timestamps por palavra` | O modelo escolhido não suporta `verbose_json`. Só `openai/whisper-large-v3`, `whisper-large-v3-turbo` e `whisper-1` suportam. `gpt-4o-transcribe` e `qwen3-asr` devolvem 400 |
| `--vicios`: aparecem vários "Obrigado" repetidos que ninguém falou | Alucinação conhecida do Whisper em PT: ele inventa "Obrigado" em trechos de silêncio. Não é bug do script. Esses cortes caem em cima de silêncio, que o `--edit` removeria de qualquer jeito, então são inofensivos. Só não conte como "gagueira real" ao reportar |
| Caminho com acento não encontrado no Bash em background (Windows) | O shell de background mangla acento (`Módulo` → não encontrado). Use PowerShell para esses caminhos |
| `Could not open input file: 432.42sec,432.96sec` | `--cut-out` aceita só uma faixa por ocorrência. Repita a flag para cada faixa, não passe várias juntas |
