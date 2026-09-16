---
name: thread-carousel
description: Cria carrossel para Instagram no estilo thread do Twitter — fundo branco, avatar e @, texto preto em parágrafos curtos, foto/card de notícia/citação por slide. A partir de um tema, pesquisa (quando for factual), escreve a copy, resolve as imagens e entrega PNG 1080×1350 pronto pra postar. Ativa em "cria um carrossel", "faz um carrossel sobre X", "carrossel estilo thread", "carrossel de print de tweet", "monta um carrossel pro Instagram", "create a carousel", "twitter thread carousel". NÃO use para post único de feed, story, Reels, legenda solta ou carrossel com identidade visual própria (fundo colorido, logo, template de marca) — este formato é só o branco estilo thread. Se o pedido for vago como "faz um post", pergunte se é carrossel antes de acionar.
argument-hint: <tema> [--slides N]
license: MIT
---

# thread-carousel

Carrossel de Instagram que imita uma thread do Twitter: fundo branco, cabeçalho
com avatar e @, texto preto em parágrafos curtos, e no máximo um bloco visual
por slide.

- **Saída:** `slide-01.png` … `slide-NN.png` em 1080×1350, mais um `preview.html`
- **Render:** Chrome ou Edge headless, que já existem na máquina. Sem Playwright,
  sem Puppeteer, sem pip install
- **Custo:** grátis, exceto se você gerar imagem no kie.ai (custa crédito, e
  nunca roda sem aprovação)

---

## Convenção de caminho

| Marcador | O que é |
|---|---|
| `<SKILL-FOLDER>` | a pasta desta skill, onde está `scripts/build-carousel.py` |
| `<OUT>` | a pasta do carrossel, uma por carrossel |

Nunca invente caminho. Se o usuário não disser onde, use
`carrosseis/<tema-em-slug>/` a partir da pasta atual.

---

## Passos

### 1. Receber o tema

O usuário passa um tema. Se ele já mandou print, foto ou screenshot, guarde os
caminhos — essas imagens entram no carrossel como estão, sem gerar nada.

Antes de escrever, decida **quantos slides**: 8 a 10 é o padrão do formato.
Menos de 6 não sustenta a promessa do gancho; mais de 10 ninguém termina.

### 2. Pesquisar — só quando o tema for factual

| Tema | O que fazer |
|---|---|
| Notícia, processo, número, data, empresa, lançamento | **Pesquise antes de escrever.** WebSearch, abra a matéria, confirme os números e guarde a URL e o nome do veículo |
| Conceito, opinião, método, bastidor, ensino | Escreva direto |

Carrossel factual com número inventado é o único jeito de esta skill causar dano
de verdade. Todo número que aparecer no carrossel tem que ter vindo de uma fonte
que você abriu.

### 3. Perfil

O cabeçalho precisa de `nome`, `arroba` e `avatar`, e eles aparecem nos **dez**
slides: errar o @ custa uma renderização inteira. Confirme com o usuário na
primeira vez, não deduza de outra rede.

Isso mora num **`config.json`** na raiz dos carrosséis. O script procura ao lado
do spec e vai subindo até 3 pastas, então um único arquivo serve para todos os
carrosséis:

```json
{
  "nome": "Anderson Adelino",
  "arroba": "@oandersonadelino",
  "avatar": "perfil.jpg"
}
```

`avatar` é relativo à pasta **do config**, não à do spec. Tem um modelo pronto
em `assets/config.example.json`.

Se um carrossel específico precisar de outro perfil (cliente, segunda conta),
basta pôr `perfil` no próprio spec: ele ganha do config.

Sem `config.json` e sem `perfil` no spec, o script para e diz o que falta. Sem
avatar ele roda, mas cai num círculo com a inicial: avise que fica bem melhor
com a foto.

### 4. Escrever a copy

A estrutura abaixo é o que faz o formato funcionar. Cada slide tem um trabalho:

| Slide | Trabalho |
|---|---|
| 1 | **Gancho:** 🚨 + o fato mais alto que você pode sustentar + promessa do que vem + 👉. **Sempre com 2 imagens lado a lado** |
| 2–3 | O que aconteceu, em linguagem de conversa, com o card da fonte real |
| 4–6 | O mecanismo: a acusação, o número, a lista de específicos (`→` por item) |
| 7–8 | Por que importa pra quem lê + **a desescalada**: "Mas calma, não é X agora" |
| 9 | Zoom-out: "isso vai muito além de…" |
| 10 | CTA: seguir pra acompanhar. Sem link, sem "clica na bio" |

A desescalada não é opcional. É ela que separa este formato de clickbait: o
gancho promete o extremo, e o meio do carrossel devolve a medida certa. Sem
isso, o slide 1 vira mentira.

**Assinatura visual:** parágrafos de 1 a 3 linhas, sempre com linha em branco
entre eles (`\n\n` no JSON). Parágrafo grande quebra o formato.

**Emoji:** 🚨 urgência · ⚠️ risco · ✅ lista · ➡️ 👉 continua · 😳 reação.
No máximo 2 por slide.

**A seta 👉 / ➡️ é promessa, não pontuação.** Use só quando o slide arma algo
que vem no próximo — "E qual foi a acusação?👉". Slide que fecha uma ideia
termina normal, ou em ⚠️ / 😳. No carrossel de referência, 3 dos 10 slides não
têm seta nenhuma. Seta em todo slide vira tique e o leitor para de acreditar
nela.

**CAPS:** no máximo uma palavra por slide (TRILHÃO, JUSTAMENTE, FUNCIONAM).
Duas já vira grito.

**Travessão é proibido.** Nunca use `—` nem `–` na copy. É a pontuação que mais
denuncia texto de IA, e ninguém escreve assim no Instagram. Onde daria vontade
de usar travessão, quebre a frase:

| Não | Sim |
|---|---|
| `investir na Anthropic — a dona do Claude` | `investir na Anthropic, a dona do Claude` |
| `ferramenta externa — incluindo o Codex` | `ferramenta externa, incluindo o Codex` |
| `o motivo é simples — dinheiro` | `o motivo é simples: dinheiro` |

Vírgula, dois-pontos ou ponto final. Nessa ordem de preferência.

#### Orçamento de caracteres

Medido no Chrome, não estimado. Acima do orçamento o texto **de todos os
slides** encolhe junto, porque o carrossel usa um único tamanho de fonte:

| Slide | Fica nos 46px até | Barra vermelha a partir de |
|---|---|---|
| Só texto | **619** caracteres | 955 |
| Com foto | **336** | 610 |
| Com card ou citação | **422** | 682 |

Escreva dentro da primeira coluna. O script avisa qual slide estourou e quanto,
antes de renderizar.

**Tem piso também: 30% do orçamento.** O conteúdo é centralizado no slide, mas
centralizar pouco texto num quadro de 1350px continua parecendo vazio. No
primeiro carrossel de verdade, um slide de citação usou 7% e outro 19%, e os
dois ficaram com cara de rascunho.

| Slide | Escreva pelo menos |
|---|---|
| Só texto | 190 caracteres |
| Com foto | 100 |
| Com card ou citação | 130 |

Se um slide não chega lá, ele não tem assunto próprio: junte com o vizinho ou
corte. Slide fraco custa mais que slide a menos, porque é onde a pessoa para de
arrastar.

**O CTA é a exceção.** O último slide é curto de propósito, e o da referência
tem 150 caracteres. Não encha ele para bater a cota.

### 5. Resolver as imagens

Nem todo slide precisa de bloco visual — na referência, metade é só texto. Use
bloco quando ele acrescenta prova, não decoração.

| O que o slide precisa | De onde vem |
|---|---|
| Print, foto ou screenshot do próprio usuário | ele manda o caminho, você usa como está |
| Foto de pessoa, empresa ou evento **real** | `baixar` a partir da matéria que você já abriu na pesquisa, ou `stock` no Pexels |
| Imagem conceitual, ilustrativa, sem pessoa real | `imagem` no kie.ai — **só depois de aprovação** |
| Manchete de notícia | bloco `card`, com veículo e título **reais** |
| Trecho de documento, lista oficial | bloco `citacao`, com `destaque` no trecho que importa |

```bash
python "<SKILL-FOLDER>/scripts/build-carousel.py" baixar "<url-da-imagem>" --out "<OUT>/img/01"
python "<SKILL-FOLDER>/scripts/build-carousel.py" stock "courtroom exterior" --out "<OUT>/img/02"
python "<SKILL-FOLDER>/scripts/build-carousel.py" imagem "prompt em ingles" --out "<OUT>/img/03" --aspect 1:1
```

Os três baixam pro disco e conferem os bytes. A extensão final sai do conteúdo,
então o comando imprime o caminho que realmente gravou — use esse.

**Antes de chamar `imagem`:** mostre o prompt ao usuário e espere o "pode".
Gerar imagem custa crédito e não dá pra desfazer a cobrança.

### 6. Montar o spec e renderizar

Um JSON, um comando. Caminhos de imagem são relativos à pasta do spec.

```json
{
  "titulo": "Meta no tribunal",
  "perfil": {"nome": "...", "arroba": "@...", "avatar": "perfil.jpg"},
  "slides": [
    {"texto": "🚨AGORA: ...\n\nVou te atualizar 👉", "imagens": ["img/01.jpg", "img/02.jpg"]},
    {"texto": "..."},
    {"texto": "...", "card": {"fonte": "g1", "cor": "#c4170c", "chapeu": "TECNOLOGIA",
                              "titulo": "manchete real", "texto": "linha de apoio"}},
    {"texto": "...", "citacao": {"texto": "...", "destaque": "trecho em amarelo"}}
  ]
}
```

- `imagens` aceita 1 (larga) ou 2 (lado a lado). Mais que isso é ignorado
- `card.cor` é a cor da tarja do veículo: g1 `#c4170c`, Folha `#12326e`,
  UOL `#001e64`, CNN `#cc0000`, Estadão `#0a3d62`
- `citacao.destaque` precisa aparecer **literalmente** dentro de `citacao.texto`,
  senão o script para
- Um bloco por slide. Dois blocos no mesmo slide é erro, não escolha

```bash
python "<SKILL-FOLDER>/scripts/build-carousel.py" montar "<OUT>/spec.json" --out "<OUT>"
```

### 7. Conferir antes de entregar

O script já confere sozinho que cada PNG existe e saiu exatamente 1080×1350 —
ele para se não saiu. O que **você** ainda precisa fazer:

1. **Abrir o `preview.html` e olhar.** Se algum slide tiver uma barra vermelha
   `TEXTO NÃO COUBE`, aquele slide não pode ser postado: encurte o texto e rode
   de novo. A barra é proposital, ela existe pra ser impossível de ignorar
2. Se o script avisou "o slide N encolhe a fonte de TODOS", encurte esse slide.
   Um slide longo demais derruba o tamanho do carrossel inteiro
3. Conferir que toda foto de pessoa real veio de fonte real, não do kie.ai

### 8. Reportar

```
✅ Carrossel pronto

📁 Pasta:   <OUT>
🖼️  Slides:  N arquivos, 1080×1350
👀 Preview: <OUT>/preview.html

Fonte: <veículo + link, quando for tema factual>
Imagens: X do usuário · Y buscadas · Z geradas no kie.ai
```

Ofereça: reescrever um slide, trocar uma imagem, mudar a ordem.

---

## Chaves

| Chave | Pra quê | Onde pegar |
|---|---|---|
| `KIE_API_KEY` | gerar imagem | https://kie.ai |
| `PEXELS_API_KEY` | banco de imagens | https://www.pexels.com/api/ |

Nenhuma das duas é obrigatória: sem elas o carrossel sai com as imagens do
usuário, com as que você baixou da web, ou só com texto. O script lê as chaves
do ambiente ou de um `.env`, e lê **só a chave que precisa** — nunca o `.env`
inteiro, que no projeto de outra pessoa está cheio de credencial alheia.

---

## Guardrails

- **Nunca gere foto realista de pessoa real identificável no kie.ai**, nem
  screenshot falso de notícia, rede social ou documento. Pessoa ou evento real →
  foto buscada ou print do usuário. Um carrossel factual com imagem fabricada é
  desinformação, mesmo quando o texto está certo
- **O bloco `card` é uma manchete real de um veículo real.** Não invente
  manchete, não invente veículo, não mude o sentido do título pra caber
- **`imagem` nunca roda sem aprovação.** Custa crédito
- **Nunca reporte "pronto" sem ter aberto o preview.** O script garante
  dimensão, não garante que a copy ficou boa nem que nenhum slide estourou
- Não sobrescreva pasta de carrossel existente — o script recusa
- Todo número factual sai de uma fonte que você abriu

---

## Problemas

| Problema | O que fazer |
|---|---|
| `nao achei Chrome nem Edge` | instale Chrome: `winget install Google.Chrome` (Windows), `brew install --cask google-chrome` (Mac) |
| Barra vermelha `TEXTO NÃO COUBE` | o slide passou de 955 caracteres (ou 610 com foto). Encurte, não tem outro jeito |
| Todos os slides saíram com fonte pequena | um slide longo derrubou o resto. O aviso do script diz qual. Encurte ele |
| `o destaque '...' nao aparece no texto da citacao` | o `destaque` tem que ser um trecho literal do `texto`, com os mesmos acentos e aspas |
| `o que veio de ... nao e imagem` | a URL era de uma página, não do arquivo. Abra a matéria e pegue o endereço da imagem em si |
| `Falta a chave KIE_API_KEY` | só acontece no comando `imagem`. Ou configure a chave, ou use `stock` / `baixar` / print do usuário |
| `kie.ai passou de 10 min` | confira os créditos em kie.ai |
| `ja tem conteudo` | escolha outra pasta de saída; a skill não sobrescreve carrossel pronto |
| Emoji saiu em preto e branco | falta fonte de emoji no sistema (raro no Windows e no Mac; no Linux instale `fonts-noto-color-emoji`) |
