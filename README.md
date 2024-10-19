# MeuBotDeLogin

Este é um bot do Telegram que permite que os usuários comprem logins de acesso a um sistema.

## Funcionalidades

- Geração de logins aleatórios
- Cadastro de logins no painel admin
- Compra de logins pelos usuários via integração com o PagSeguro

## Configuração

1. Crie um banco de dados MySQL e configure as credenciais no arquivo `src/config.php`.
2. Substitua `'7596236062:AAG8Qf6goDFzE1bdWjpmePt31aM7P_tSOOo'` no arquivo `src/config.php` pelo token do seu bot do Telegram.
3. Substitua `'SEU_CODIGO_PAGSEGURO'` no arquivo `src/index.php` pelo seu código de integração com o PagSeguro.
4. Instale as dependências usando o Composer:
5. 
