namespace Billing.Services
{
    public interface IInvoiceService { List<Invoice> Search(string c); void Pay(int id, decimal amount); }

    public class InvoiceService : IInvoiceService
    {
        private readonly BillingContext _db;
        private readonly string _cs;
        public InvoiceService(BillingContext db, IConfiguration config)
        {
            _db = db;
            _cs = config.GetConnectionString("BillingDb");
        }
        public List<Invoice> Search(string c)
        {
            return _db.Invoices.Where(i => i.Customer == c).ToList();
        }
        public void Pay(int id, decimal amount)
        {
            using (var conn = new SqlConnection(_cs))
            {
                var cmd = new SqlCommand("usp_PayInvoice", conn);
                cmd.CommandType = CommandType.StoredProcedure;
                cmd.ExecuteNonQuery();
            }
        }
    }
}
