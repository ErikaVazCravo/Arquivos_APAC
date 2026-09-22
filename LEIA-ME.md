# Editor APAC

Abra **Editor_APAC.exe** com dois cliques. O aplicativo abre diretamente no navegador, na aba **Editor APAC**, sem janela de terminal ou tela inicial de desktop. Não é necessário instalar Python no computador de uso.

O editor funciona localmente, no próprio computador, sem publicar os arquivos na internet. Use **Encerrar**, no canto superior direito, para finalizar o aplicativo. Fechar apenas a aba do navegador não encerra o processo local.

## Editar no navegador

1. Na primeira aba, **Editor APAC**, clique em **Abrir arquivo APAC**.
2. Selecione o arquivo na janela de escolha do Windows.
3. Pesquise pelo número, nome do paciente ou CNES na lista à esquerda, ou use **Primeira, Anterior, Próxima e Última**.
4. Edite os campos nas seções **Dados da APAC**, **Dados complementares**, **Procedimentos** e **Cabeçalho do arquivo**.
5. Clique em **Salvar alterações** para gravar no arquivo aberto, ou **Salvar como…** para criar uma cópia e continuar trabalhando nela.

O salvamento sobre o arquivo original cria um backup na primeira gravação. Alterar o número ou a competência da APAC atualiza também seus procedimentos e laudos associados. Ao trocar de APAC, abrir outro arquivo ou entrar na consulta com alterações pendentes, você pode salvar, descartar ou cancelar. Alterações no arquivo feitas por outro programa são detectadas antes de gravar.

## Consultar as fichas

1. Abra o arquivo na primeira aba.
2. Clique na segunda aba, **Dados para digitação da APAC**.
3. A ficha da APAC selecionada aparece dentro da própria página. Use **Visualizar todas as APACs** para abrir a lista pesquisável.
4. Cada registro de APAC tem sua ficha, com identificação, procedimentos, dados complementares e solicitação/autorização. Use **Voltar ao editor** para editar novamente.

As fichas são somente para leitura. Os controles disponíveis servem para pesquisar, navegar e imprimir/salvar PDF. Cada ficha pode ocupar mais de uma folha na impressão, conforme a quantidade de procedimentos. A edição continua disponível exclusivamente no editor do aplicativo.

A consulta é atualizada ao voltar à segunda aba depois de salvar. Os arquivos HTML ficam em uma pasta temporária local e são removidos ao encerrar o aplicativo. Para guardar uma ficha, use **Imprimir / Salvar PDF**. Os dados do arquivo APAC não são alterados pela consulta.

## Descrições dos procedimentos

Mantenha a pasta **Tabelas_Sigtap** ao lado de **Editor_APAC.exe**. São aceitos os pacotes ZIP originais ou os TXT extraídos, inclusive em subpastas. Os arquivos `tb_procedimento.txt` e `tb_procedimento_layout.txt` devem permanecer juntos. O aplicativo lê o layout fornecido na própria tabela.

As tabelas são carregadas na abertura. Depois de adicionar uma competência, clique em **Recarregar SIGTAP**, no rodapé. Não é necessário gerar outro executável para atualizar essas tabelas.

A descrição usa preferencialmente a competência da APAC. Se ela não estiver disponível, usa a competência anterior mais próxima ou, na ausência desta, a primeira disponível. A ficha indica explicitamente a competência utilizada e a diferença. Isso apenas fornece o nome para consulta; não valida vigência, compatibilidade ou regras de faturamento. Para correspondência exata, adicione o SIGTAP da competência do arquivo.

Também é possível importar CSV com cabeçalho `codigo;descricao`, códigos de dez dígitos (com ou sem pontuação) e codificação UTF-8 ou Windows-1252. O CSV não possui controle de competência.

O arquivo APAC não contém todas as informações apresentadas pelo SIA: por exemplo, nomes de municípios/estabelecimentos e CPF do médico/autorizador não estão no layout implementado. Informações ausentes, campos vazios e descrições não encontradas ficam **em branco** na ficha. Não são inferidos nomes ou documentos.

## Gerar novamente o executável (desenvolvimento)

No Windows, com Python e Tkinter instalados:

```powershell
python -m pip install -r requirements-build.txt
python -m unittest discover -s tests -v
python build_executable.py
```

O arquivo `Editor_APAC.exe` é gerado nesta pasta. A configuração utiliza `--onefile --windowed`, conforme a [documentação do PyInstaller](https://pyinstaller.org/en/stable/usage.html).
