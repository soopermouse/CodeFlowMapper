using Billing.Services;
using Microsoft.AspNetCore.Mvc;

namespace Billing.Controllers
{
    [Authorize(Roles = "Finance")]
    public class InvoicesController : Controller
    {
        private readonly IInvoiceService _invoices;

        public InvoicesController(IInvoiceService invoices)
        {
            _invoices = invoices;
        }

        [HttpGet]
        public IActionResult Index(string customer)
        {
            var list = _invoices.Search(customer);
            return View(list);
        }

        [HttpPost]
        public IActionResult Pay([FromForm] PaymentModel model)
        {
            if (!ModelState.IsValid)
            {
                ModelState.AddModelError("Amount", "The amount is not valid");
                return View("Index");
            }
            _invoices.Pay(model.InvoiceId, model.Amount);
            return RedirectToAction("Index");
        }
    }
}
