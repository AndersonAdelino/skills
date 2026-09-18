# cpanel-deploy

Publica uma pasta de site estático num cPanel e **confere se o endereço no ar é
mesmo a página nova**.

Serve qualquer pasta pronta: feita à mão, gerada por outra skill, ou saída de
Hugo, Astro, Vite, Eleventy, Jekyll.

```bash
cd clientes/padaria
python scripts/deploy-cpanel.py --dry-run
python scripts/deploy-cpanel.py
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

**Python 3.** Só isso. Nada de `pip install`, FTP, rsync ou runner de CI.

## Config: uma conta, vários clientes

```
projeto/.env                      CPANEL_HOST, CPANEL_USER, CPANEL_TOKEN
projeto/clientes/padaria/.env     DEPLOY_PATH, SITE_URL
projeto/clientes/oficina/.env     DEPLOY_PATH, SITE_URL
```

O script sobe até 4 pastas juntando os `.env`, e o mais próximo ganha. O token
fica num lugar só, e cada cliente diz apenas para onde vai. Modelo em
`.env.example`.

## O que ele confere sozinho

| | |
|---|---|
| `.env` no git | recusa rodar. Token commitado é irreversível |
| `.env` alheio | lê só as chaves do cPanel, nunca o arquivo inteiro |
| **Site de outro cliente no destino** | para, mostrando os dois títulos. `--forcar` passa por cima |
| `index.php` na pasta | avisa: o Apache serve ele antes do `index.html` novo |
| Imagem > 500 KB | avisa |
| Resposta do cPanel | lê o JSON de verdade, status do topo e por arquivo |
| **A URL publicada** | busca e compara o `<title>`. Sai com código 1 se não bater |

O token nunca é impresso nem passa por linha de comando.

## Limites conhecidos

- **Só cPanel.** Não faz Vercel, Netlify, S3 nem FTP puro
- **Só arquivo estático.** Não instala nada, não roda build, não toca em banco
- **Não apaga nada no servidor.** Sobrescreve arquivo por arquivo; lixo antigo
  fica até você limpar pelo painel
- **Um arquivo por requisição.** 40 imagens são 40 viagens. Funciona, não é rápido
- **`--inseguro` existe** para quando o cPanel responde com o certificado do
  servidor em vez do domínio. O token viaja nessa conexão: só use nesse caso

## O que a gente descobriu publicando de verdade

Cada item abaixo tem teste, e todos foram encontrados contra uma HostGator real:

- **403 `error code: 1010` não é o token**, é o Cloudflare recusando requisição
  sem `User-Agent`
- **`Fileman::mkdir` não existe** nesta versão do cPanel. O `upload_files` cria
  a árvore sozinho
- **Sem `overwrite=1` o segundo deploy falha em todos os arquivos** — que é a
  operação mais comum, republicar depois de um ajuste
- **O `status` do UAPI não se lê por busca de texto:** `upload_files` devolve um
  status por arquivo dentro de `data`, então resposta de erro pode conter
  `"status":1` aninhado. A versão anterior deste script, em bash, reportava
  sucesso sem ter subido nada por causa disso
- **406 para User-Agent curto** (mod_security). Seu monitor de uptime precisa
  mandar UA de navegador, ou vai acusar site fora do ar com o site no ar

Detalhes de HostGator, limites de plano e segurança de conta compartilhada em
`references/hostgator.md`.

## Teste

```bash
python scripts/deploy-cpanel.py --autoteste
```

Sem rede, sem chave, sem tocar em servidor. Roda no CI a cada push.

## Licença

MIT.
