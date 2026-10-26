package com.acme.orders.service;
import java.util.List;
public interface OrderService {
    List<Order> findOrders(String status);
    void createOrder(OrderRequest r);
}
