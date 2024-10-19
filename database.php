<?php
$servername = "localhost";
$username = "seuusuario";
$password = "suasenha";
$dbname = "seu_banco_de_dados";

$db = new mysqli($servername, $username, $password, $dbname);

if ($db->connect_error) {
    die("Falha na conexão com o banco de dados: " . $db->connect_error);
}
