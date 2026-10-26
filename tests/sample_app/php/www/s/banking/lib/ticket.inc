<?php
class BankTools {
    public static function checkIBAN($iban) { return preg_match('/^[A-Z]{2}\d{2}/', $iban); }
    public static function getCurrencies() { return array('EUR', 'USD'); }
}
class Logger { public static function log($m) { error_log($m); } }
class OldDatabase { function __construct($c) {} function getData($sql) { return array(); } }
