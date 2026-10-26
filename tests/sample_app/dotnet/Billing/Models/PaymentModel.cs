public class PaymentModel
{
    [Required(ErrorMessage = "Invoice is required")]
    public int InvoiceId { get; set; }
    [Range(0.01, 100000, ErrorMessage = "Amount must be between 0.01 and 100000")]
    [Display(Name = "Amount paid")]
    public decimal Amount { get; set; }
}
