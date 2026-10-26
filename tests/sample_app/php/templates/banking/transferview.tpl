<h2>Transfer detail</h2>
<form method="post" action="transfer.html">
<input type="hidden" name="action" value="cancel">
<input type="hidden" name="id" value="{$row.id}">
<input type="submit" value="Cancel transfer" onclick="return confirm('Are you sure you want to cancel this transfer?')">
</form>
