# thread-carousel

Carrossel de Instagram no estilo thread do Twitter: fundo branco, cabeçalho com
avatar e @, texto preto em parágrafos curtos, e no máximo um bloco visual por
slide — foto, card de notícia ou citação com destaque.

Você dá o tema. A skill pesquisa (quando o tema é factual), escreve a copy,
resolve as imagens e entrega os PNG em 1080×1350, prontos pra subir.

```
/thread-carousel o processo dos 29 estados contra a Meta
```

## O que sai

```
carrosseis/meta-tribunal/
├── slide-01.png … slide-09.png   1080×1350, prontos pro Instagram
├── preview.html                  todos lado a lado, pra conferir
├── spec.json                     a copy, editável — mude e rode de novo
├── img/                          as imagens baixadas ou geradas
└── html/                         as páginas que viraram PNG
```

## Instalação

```
npx skills add AndersonAdelino/skills
```

Ou, com o marketplace:

```
/plugin marketplace add AndersonAdelino/skills
/plugin install adelino-skills@adelino
```

## Dependências

**Python 3** e **Chrome ou Edge**. Nada de `pip install`: o script só usa a
biblioteca padrão, e o Chrome que renderiza os slides é o que você já tem
instalado. Se não houver nenhum dos dois, a skill diz o comando de instalação da
sua plataforma.

## Chaves (opcionais)

| Chave | Pra quê | Custo |
|---|---|---|
| `KIE_API_KEY` | gerar imagem por IA em [kie.ai](https://kie.ai) | crédito por imagem |
| `PEXELS_API_KEY` | banco de imagens [Pexels](https://www.pexels.com/api/) | grátis |

Sem chave nenhuma o carrossel continua saindo: com os seus prints, com imagens
que a skill baixa da própria matéria pesquisada, ou só com texto. Veja
`.env.example`.

A skill lê **só a chave que precisa**, nunca o `.env` inteiro — ela costuma ser
instalada dentro do projeto de outra pessoa.

## Como o texto é dimensionado

O carrossel inteiro usa **um único tamanho de fonte**: o maior entre 46px e 36px
em que todos os slides cabem. Fonte diferente por slide renderiza sem erro
nenhum e entrega um carrossel com cara de amador.

Os limites foram medidos no Chrome, com busca binária sobre prosa em português:

| Slide | Fica nos 46px até | Não cabe mais a partir de |
|---|---|---|
| Só texto | 619 caracteres | 955 |
| Com foto | 336 | 610 |
| Com card ou citação | 422 | 682 |

Um slide acima da primeira coluna encolhe **todos** os outros — então o script
avisa qual é o culpado antes de renderizar. Um slide acima da segunda coluna sai
com uma tarja vermelha `TEXTO NÃO COUBE` no próprio PNG, de propósito: um
carrossel quebrado tem que ser impossível de postar por distração.

## Limites conhecidos

- **Só este estilo.** Fundo branco estilo thread. Não faz template de marca, nem
  fundo colorido, nem logo
- **Não posta.** Entrega os arquivos; a publicação é sua
- **Fonte do sistema**, não a Chirp do Twitter. Segoe UI no Windows, San
  Francisco no Mac — parecidas o bastante, e sem depender de download na hora do
  render, que sai errado sem avisar
- **Não gera foto de pessoa real.** Por decisão, não por limitação: imagem
  fabricada em carrossel factual é desinformação. Pessoa ou evento real entra
  como foto buscada ou print seu
- Emoji usa a fonte de emoji do sistema. No Linux, instale
  `fonts-noto-color-emoji` ou eles saem em preto e branco

## Uso direto do script

A skill faz tudo isso sozinha, mas o script funciona solto:

```bash
python scripts/build-carousel.py montar spec.json --out saida/
python scripts/build-carousel.py baixar "<url>"        --out saida/img/01
python scripts/build-carousel.py stock  "courtroom"    --out saida/img/02
python scripts/build-carousel.py imagem "<prompt>"     --out saida/img/03
python scripts/build-carousel.py --autoteste
```

## Licença

MIT.
