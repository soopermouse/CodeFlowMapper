<?php
class Transfer {
    private $db;
    function __construct() {
        $this->db = new OldDatabase(Registry::getInstance('mainBO'));
    }
    /** list transfers of an account */
    public function getTransfers($account, $status) {
        if (!BankTools::checkIBAN($account)) {
            throw new Exception("Invalid account number");
        }
        $sql = "SELECT v.id, v.amount, v.status FROM Virements v JOIN Accounts a ON a.id = v.account_id WHERE a.number = '" . $account . "' AND v.status = '" . $status . "'";
        return $this->db->getData($sql);
    }
    public function cancelTransfer($id) {
        $res = DBwrapper::requestML('Virements.VirCancel', array('id' => $id));
        $this->db->getData("EXEC sp_VirSetStatus @id = " . intval($id) . ", @status = 'C'");
        Logger::log('cancel ' . $id);
        return $res;
    }
}
