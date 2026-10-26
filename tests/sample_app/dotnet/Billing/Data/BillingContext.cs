public class BillingContext : DbContext
{
    public DbSet<Invoice> Invoices { get; set; }
}
[Table("tbl_invoice")]
public class Invoice { public int Id { get; set; } public string Customer { get; set; } }
