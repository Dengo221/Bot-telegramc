<?php
require_once 'config.php';
require_once 'database.php';

// Biblioteca do Telegram
require_once '../vendor/autoload.php';
use Telegram\Bot\Api;
use Telegram\Bot\Keyboard\Keyboard;
$telegram = new Api($bot_token);

// Comando /start
$telegram->addCommand('start', function ($update) use ($telegram, $bot_name) {
    $chat_id = $update->getMessage()->getChat()->getId();
    $text = "Olá! Eu sou o bot de logins do {$bot_name}. O que você deseja fazer?";

    $keyboard = Keyboard::make()
        ->inline()
        ->row(Keyboard::inlineButton(['text' => 'Comprar login', 'callback_data' => 'comprar']));

    $telegram->sendMessage(['chat_id' => $chat_id, 'text' => $text, 'reply_markup' => $keyboard]);
});

// Callback de botões
$telegram->onCallback(function ($update) use ($telegram, $db) {
    // Código da lógica de compra de login
});
