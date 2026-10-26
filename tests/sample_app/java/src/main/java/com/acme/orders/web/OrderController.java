package com.acme.orders.web;

import com.acme.orders.service.OrderService;
import com.acme.orders.dto.OrderRequest;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.*;
import javax.validation.Valid;

@Controller
@RequestMapping("/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/list")
    @PreAuthorize("hasRole('ORDERS_VIEW')")
    public String list(@RequestParam("status") String status, Model model) {
        model.addAttribute("orders", orderService.findOrders(status));
        return "orders/list";
    }

    @PostMapping("/create")
    public String create(@Valid @RequestBody OrderRequest request) {
        orderService.createOrder(request);
        return "redirect:/orders/list";
    }
}
