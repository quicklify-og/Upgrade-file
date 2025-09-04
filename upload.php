<?php
// ---- Quicklify upload.php ----
error_reporting(0);
header("Content-Type: text/html; charset=utf-8");

// CHANGE THIS to your full base URL:
$BASE_URL = (isset($_SERVER['HTTPS']) && $_SERVER['HTTPS'] === 'on' ? "https" : "http")
            . "://".$_SERVER['HTTP_HOST']."/";

$dir = __DIR__ . "/uploads/";
if (!is_dir($dir)) mkdir($dir, 0775, true);

if (!isset($_FILES['image'])) { echo "❌ No file."; exit; }

$f = $_FILES['image'];
$allowed = ['image/png','image/jpeg','image/webp','image/gif'];
if ($f['error'] !== UPLOAD_ERR_OK) { echo "❌ Upload error."; exit; }
if (!in_array(mime_content_type($f['tmp_name']), $allowed)) { echo "❌ Only images allowed."; exit; }
if ($f['size'] > 5*1024*1024) { echo "❌ Max 5MB."; exit; }

$ext = pathinfo($f['name'], PATHINFO_EXTENSION);
$name = uniqid("qlfy_", true) . "." . strtolower($ext);
$target = $dir . $name;

if (move_uploaded_file($f['tmp_name'], $target)) {
  $link = rtrim($BASE_URL, '/') . "/uploads/" . $name;
  echo "✅ Uploaded!<br>Image Link: <a href=\"$link\" target=\"_blank\">$link</a>";
} else {
  echo "❌ Failed to save file.";
}