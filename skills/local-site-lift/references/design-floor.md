# Design floor

## Antes de tudo: contenção não é vazio

Este documento já foi só uma lista de proibições, e o resultado saiu duas vezes:
site plano, sem contraste, com metade da tela vazia. Um agente lendo só
"evite isto" joga seguro, e seguro parece barato.

**O chão abaixo é numérico e medido.** Rode antes de mostrar qualquer coisa:

```bash
python scripts/aferir.py dist/
```

Os limites saíram de **medir seis sites institucionais reais** que o cliente
considera excelentes, não de teoria. A primeira versão deles foi inventada e
reprovava 6 de 6.

| | Mínimo | A referência mais discreta dos seis tem |
|---|---|---|
| Estados `:hover` | **12** | 16 — o site reprovado tinha **2** |
| `transition` | **20** | 29 — o reprovado tinha **1** |
| `box-shadow` | **8** | 10 — o reprovado tinha **1** |
| Grade de várias colunas no desktop | **1** | todos têm, de 7 a 74 |

Não é questão de gosto: é **ordem de grandeza**. Um site que responde ao cursor
em 2 lugares e um que responde em 100 não estão na mesma categoria de produto.

**Nunca ponha `max-width` em `ch` num título.** `h1 { max-width: 18ch }` foi o
defeito central de um site real: o título quebrava em três linhas curtas e
metade da tela ficava vazia ao lado. `ch` é para parágrafo.

### O que NÃO medir

Contar tamanhos de fonte no CSS **não mede nada**: os seis têm de 10 a 48,
porque o arquivo traz tema e plugin inteiros. O mesmo vale para `<footer>` —
4 dos 6 usam `<div class="footer">`. Tentei as duas checagens e as duas
reprovavam todo mundo.

Passar no chão não faz um site bonito. **Falhar garante um que parece barato.**

## Seis referências, e o que copiar delas

Sites institucionais brasileiros que o cliente considera excelentes. Abra pelo
menos um antes de desenhar:

- https://interprocess.com.br/
- https://allserviceindustrial.com.br/
- https://spaceclass.com.br/
- http://savassiagronegocio.com.br/
- https://pontualtecnologia.com.br/
- https://megalihub.com.br/

O que todos fazem, e que um site amador não faz:

**Herói de duas colunas com peso real.** Texto de um lado, imagem do outro,
cada um ocupando perto de metade da largura. Nada de coluna estreita à esquerda
com a tela vazia à direita.

**Título que domina a primeira tela.** Três linhas grandes, não um subtítulo
tímido. No interprocess o `h1` ocupa metade da largura e quase um terço da
altura visível.

**Imagem composta, não solta.** Mockup sobreposto à foto, com sombra e
recorte. O trabalho aparece na imagem, e é isso que faz parecer caro.

**Ritmo entre seções.** Herói assimétrico, depois seção centrada, depois grade.
O olho sabe onde uma acaba. Fundo alternado ajuda.

**Algo flutuante e útil.** WhatsApp fixo, um vídeo curto de depoimento no
canto. Dá sinal de vida sem atrapalhar.

## O desktop não é o celular esticado

"Mobile primeiro" é ordem de construção, não desculpa para nunca desenhar o
desktop. Numa tela de 1440px:

- o conteúdo usa a largura. Uma coluna de 420px alinhada à esquerda, com o
  resto vazio, é o erro mais visível que existe
- pelo menos uma seção tem duas colunas de verdade: texto de um lado, imagem
  ou lista do outro
- o herói ocupa a primeira tela com intenção: título grande, uma linha de
  apoio, um botão, e uma imagem que não é enfeite
- seções alternam fundo, para o olho saber onde uma acaba



Direção visual destilada para site de comércio local. Use como chão de qualidade, não como lista de efeitos.

Inspirado em técnicas de direção de frontend (escolha deliberada, assunto primeiro, um gesto ousado) e em craft de produção (um ciclo de inspeção, anti-padrão, acessível no celular). Reescrito para este método. Não copie skills de terceiros.

## O assunto manda

A cara do site sai do negócio real: farinha e forma, óleo e metal, jaleco, cadeira de salão, cheiro de pão. Paleta, tipo e foto vêm daí. Se o plano visual serviria igual para um SaaS, descarte.

Gaste ousadia em um lugar só — hero, tipo de título ou uma foto grande. O resto fica quieto.

## Plano antes do código

Em `DESIGN.md` fixe:

- 4 a 6 cores nomeadas (hex), com papel (fundo, texto, ação, apoio)
- uma família para título e uma para texto, ou uma só
- layout em uma frase + wire ASCII da home no mobile
- o elemento que a pessoa vai lembrar

Revise o plano contra a lista de defaults abaixo. Se qualquer eixo livre caiu num default, troque e anote o porquê. Só então escreva HTML.

## Técnica não é clichê: o que separa é a execução

Esta lista já foi mais longa e proibia coisas que sites institucionais bons
fazem o tempo todo. Conferido: o [interprocess.com.br](https://interprocess.com.br/)
usa **eyebrow em caixa alta** ("TECNOLOGIA EM ONCOLOGIA") e **uma palavra do
h1 em outra cor** ("Soluções *Especializadas*"), e funciona nos dois casos.

O problema nunca foi a técnica. É usá-la **sem conteúdo**:

| Ruim | Bom |
|---|---|
| eyebrow genérico: `SOLUÇÕES INOVADORAS` | eyebrow que informa: `TECNOLOGIA EM ONCOLOGIA` |
| palavra colorida escolhida ao acaso | a palavra que **é** a oferta |
| `01 / 02 / 03` decorando três cards | numeração onde existe sequência de verdade |

Se o elemento sobrevive a "isso diria a mesma coisa para outro negócio?",
apague. Se é específico deste negócio, use sem culpa.

## O que ainda denuncia site gerado

Estes continuam valendo, porque são falta de decisão, não técnica:

- creme quente + serif + terracota, sem o brief ter pedido
- fundo preto + um neon
- **kit SaaS: cards idênticos, mesma sombra, mesmo raio, wash de degradê** em
  tudo, sem hierarquia entre eles
- meta com ponto médio (`A · B · C`) como enfeite
- seta `→` no fim de **todo** botão
- Inter / Arial / Roboto como personalidade, sem nenhuma escolha de tipo
- glassmorphism, texto em degradê, grid decorativo de linhas

O teste é o mesmo: o elemento diz algo sobre **este** negócio, ou é textura?

## Tipo, cor, espaço, motion

Tipo carrega personalidade. Duas famílias no máximo, escala curta, linha de texto abaixo de ~80 caracteres. Título pode ser o gesto. Texto corre sem frescura.

Cor tem dono. Uma cor de ação (o botão do WhatsApp). Fundo e texto com contraste real. Variáveis CSS na `:root`.

Espaço é ritmo, não margem aleatória. Seções respiram. No mobile, o dedo precisa do botão grande e do número visível sem pinça.

## Movimento: anima sempre, com saída explícita

**Decisão do dono destas skills: o site anima sempre**, sem obedecer
`prefers-reduced-motion` por padrão.

O motivo é empírico. No Windows esse sinal quase sempre significa "desliguei
efeito visual por desempenho", não "movimento me dá enjoo" — a opção fica em
Efeitos Visuais e muita gente desliga sem pensar em acessibilidade. Obedecer
entregava um site morto para a maioria de quem tem o sinal ligado, e foi o que
aconteceu na máquina dele.

A saída existe e é explícita: **`?anim=0`**.

```html
<!-- no <head>, ANTES do CSS, para não piscar -->
<script>
if (/[?&]anim=0/.test(location.search))
  document.documentElement.setAttribute('data-sem-anim', '');
</script>
```

```css
html[data-sem-anim] * {
  transition-property: color, background-color, border-color, box-shadow, opacity !important;
  animation: none !important;
}
html[data-sem-anim] *:hover { transform: none !important; }
html[data-sem-anim] [data-revela] > * { opacity: 1 !important; transform: none !important; }
```

Repare que mesmo no modo reduzido **cor, opacidade e sombra continuam**: elas
não movem nada, e são o que faz o site responder ao cursor. O que some é só
transformação — deslizar, escalar, parallax, revelação no scroll.

O script tem que rodar no `<head>`, antes do CSS. Depois, o conteúdo já pintou
e a troca pisca.

### Revelação no scroll: duas armadilhas que deixam o site em branco

**1. O CSS nunca esconde nada sozinho.** Se `.anima { opacity: 0 }` estiver no
arquivo e o JS falhar, não for baixado ou o observer não disparar, o site fica
**em branco**. Quem esconde é o JS:

```js
raiz.setAttribute('data-anima', '');   // só agora pode sumir: há JS para revelar
```

```css
.anima { opacity: 1; }                        /* sem JS, visível */
html[data-anima] .anima { opacity: 0; transform: translateY(26px); }
html[data-anima] .visivel .anima { opacity: 1; transform: none; transition: … }
```

E uma rede de segurança que **remove o atributo da raiz**, desligando toda
regra de esconder de uma vez, sem depender de classe certa em elemento nenhum:

```js
setTimeout(function () { raiz.removeAttribute('data-anima'); }, 2600);
```

**2. Não confie no observer para o que já está na tela.** O herói está sempre
visível no carregamento, e ficar refém de um callback é o que o deixou
invisível num teste real. Revele na segunda pintura o que já está no viewport,
e use o observer só para o resto:

```js
requestAnimationFrame(function () { requestAnimationFrame(function () {
  secoes.forEach(function (s) {
    var r = s.getBoundingClientRect();
    if (r.top < innerHeight && r.bottom > 0) revelar(s);
  });
}); });
```

**Cuidado com a cascata.** Uma regra `.heroi .anima { opacity: 0 }` escrita
*depois* da regra que revela tem a **mesma especificidade** e ganha por vir
depois: o herói some para sempre. Esconder e revelar, dois passos, sem exceção
por seção.

Fora isso: motion responde a um gesto (abrir menu, passar o cursor) ou a um
único momento de entrada. Fade e slide em **toda** seção é default de IA.

## Imagem exibida maior que o nativo borra

Foto do perfil do Google tem no máximo o que a pessoa subiu. No caso testado,
1440×809 — e `negocio.py` já pede `=s0`, que é esse teto. Não existe maior.

- **limite a largura de exibição à largura real do arquivo.** Uma banda com
  `max-width: 1200px` a partir de um arquivo de 1440px fica nítida; a mesma
  imagem em `width: 100%` num monitor de 1920 é ampliação, e aparece
- foto noturna de celular tem ruído. `unsharp=5:5:0.8` no ffmpeg ajuda, e nela
  vale subir a qualidade do webp para 90+

## Chão de produção

O site sobe em hospedagem compartilhada e é aberto no 4G, no sol, com uma mão.

- legível no celular de 360px sem scroll horizontal
- contraste de texto suficiente
- foco de teclado visível
- imagens com tamanho realista (não 4k no hero)
- um `h1`, heading em ordem
- tap targets de CTA com área folgada

## Imagem

Foto de site de negócio é **afirmação sobre o negócio**. Uma recepção bonita
gerada por IA diz "esta é a nossa recepção", e não é. Isso não é estilo, é
mentira ao cliente do cliente.

**Quem decide é você, não o script.** `scripts/imagens.py` só executa: `buscar`
lista, `pegar` baixa o id que você escolheu, `gerar` usa o prompt que você
escreveu. Ele nunca troca de fonte sozinho.

### Primeiro: essa imagem afirma algo sobre este negócio?

Fachada, recepção, sala, equipamento, equipe, o produto que eles fazem, o prato
que eles servem. Se sim, ela **só pode ser foto real deles**. Vale mesmo mal
enquadrada. Não existindo foto real, **a seção não leva imagem** — um bloco de
texto honesto é melhor que uma foto que mente.

Onde procurar, em ordem de quem entrega:

| | |
|---|---|
| **Perfil do Google** | `scripts/negocio.py`. A única que funcionou no primeiro site real |
| O dono | pede. É a melhor, e a que ninguém lembra de pedir |
| Site atual | confira: costuma ser banco de imagem. No primeiro teste, era |
| Instagram, Facebook | bloqueiam requisição sem login |

Foto do perfil do Google é mistura de foto do dono e de cliente, e pode ter
rosto de funcionário. **Rosto identificável não se publica sem consentimento.**
Toda foto daí é candidata marcada no `PRODUCT.md`, nunca publicação direta.

Nunca gere: pessoa real identificável, documento, print de notícia, selo,
certificado, avaliação.

### Depois: o que a imagem precisa ser?

| Se... | Use | Porque |
|---|---|---|
| é um **assunto comum do mundo real**, que alguém já fotografou | **Pexels** | pão saindo do forno, mãos de idoso, rua de interior, criança no colo, cadeira de dentista. Se você consegue imaginar essa foto existindo num banco, ela existe |
| é **específico da ideia deste site**, e não existiria como stock | **kie.ai** | uma composição na paleta da marca, uma cena que amarra com a manchete, uma textura, um padrão de fundo, um ícone que combina com o resto |

O teste prático: **busque no Pexels primeiro**, porque é grátis e a busca já
responde a pergunta. Olhe as prévias. Se o que voltar serve, acabou. Se voltar
genérico demais, fora de tom, ou nada com o que a copy diz, **é sinal de que a
imagem é específica demais para stock** — aí gere.

```bash
python scripts/imagens.py buscar "pao saindo do forno padaria" --n 5 --previa /tmp/p
# olhe as previas, escolha
python scripts/imagens.py pegar 7447284 --out dist/img/hero
# se nada servir:
python scripts/imagens.py gerar "<prompt em ingles>" --out dist/img/hero
```

Busque em **inglês**: o acervo do Pexels é muito maior. Escolher às cegas dá
errado — numa busca por "família feliz" para uma clínica no Seridó, o primeiro
resultado foi uma marina com bandeira dos EUA.

### Depois de escolher

- **Crédito no rodapé.** O comando imprime o autor. A licença do Pexels não
  exige, mas credite
- **Uma linha no `PRODUCT.md`** avisando o dono de que aquilo é ilustrativo e
  pode ser trocado por foto real das instalações dele
- O `imagens.py` já redimensiona e converte para webp. Acima de 150 KB ele
  reclama: atenda

## Depoimento

Só com nome e data reais. A fonte natural é o perfil do Google do negócio, que
é público.

**Leia as avaliações ruins também, e conte ao dono.** Elas quase sempre apontam
um problema operacional que o site não conserta e não deve esconder. Se a
queixa recorrente for "demora" ou "desorganização", isso é informação de
negócio mais valiosa que o site inteiro, e a copy não pode prometer o contrário
do que os clientes relatam.

Nunca publique nota agregada que você não conseguiu verificar. Sem
`aggregateRating` no schema por dedução.

## Cópia

Palavra é design. Frase curta. Voz ativa. CTA diz o que acontece: "Chamar no WhatsApp", "Ver no mapa".

**Travessão é proibido.** Nunca `—` nem `–` em texto que o cliente lê. É a
pontuação que mais denuncia texto gerado, e ninguém escreve assim. Onde daria
vontade de usar, quebre a frase:

| Não | Sim |
|---|---|
| `Rua Manoel Felipe, 23 — CEP 59300-000` | `Rua Manoel Felipe, 23. CEP 59300-000` |
| `Clínica Fácil — consultas e exames` | `Clínica Fácil: consultas e exames` |

Ponto, vírgula ou dois-pontos. O ponto médio (`A · B · C`) também não serve:
já está na lista de defaults que denunciam site gerado.

Não venda o sistema. Fale o que o cliente ganha na cidade dele. Horário, bairro e "fica em frente a X" valem mais que slogan.

Estado vazio e erro (mapa que não carrega, foto ausente) explicam o próximo passo. Não façam graça.
