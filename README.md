# 📡 Meu Servidor RSS Gratuito (Alternativa ao RSS.app)

Este projeto transforma qualquer site (HTML normal ou dinâmico em JavaScript/React) em feeds RSS 2.0 e publica tudo gratuitamente usando **GitHub Actions + GitHub Pages**.

---

## 🚀 Como colocar no ar (100% Grátis)

### Passo 1: Subir para um repositório no GitHub
1. Crie uma conta ou acesse seu [GitHub](https://github.com).
2. Crie um **novo repositório Público** (ex: `meus-feeds-rss`).
   *(Importante: repositórios públicos têm GitHub Pages e minutos de GitHub Actions **ilimitados e gratuitos**).*
3. Envie os arquivos desta pasta para lá.

### Passo 2: Ativar o GitHub Pages
1. No seu repositório do GitHub, clique na aba **Settings** (Configurações).
2. No menu lateral esquerdo, clique em **Pages**.
3. Em **Build and deployment > Source**, mude de *Deploy from a branch* para **GitHub Actions**.

### Passo 3: Testar!
1. Vá na aba **Actions** do seu repositório.
2. Clique em **Atualizar Feeds RSS e Publicar no GitHub Pages** e depois no botão **Run workflow**.
3. Em cerca de 1 minuto, seu painel estará online no endereço:
   `https://SEU-USUARIO.github.io/meus-feeds-rss/`

---

## ➕ Como adicionar novos sites pelo navegador

Você não precisa mexer em código Python! Tudo fica no arquivo [`feeds.json`](./feeds.json):

1. Abra o seu Painel Web (`https://SEU-USUARIO.github.io/meus-feeds-rss/`) e clique no botão **"+ Gerar Novo Feed (JSON)"**.
2. Preencha a URL do site, escolha se ele é **Automático** (descobre as notícias sozinho) ou **Manual** (com seletores CSS) e se precisa de **JavaScript**.
3. Clique em **Copiar JSON**.
4. No GitHub, abra o arquivo `feeds.json`, clique no ícone de lápis (**Edit**), cole o novo site na lista e clique em **Commit changes**.
5. O GitHub Actions vai rodar na mesma hora e criar o novo link `.xml`!
