package com.acme.orders.service;

import com.acme.orders.repo.OrderRepository;
import org.springframework.jdbc.core.JdbcTemplate;

@Service
public class OrderServiceImpl implements OrderService {
    private final OrderRepository orderRepository;
    private final JdbcTemplate jdbcTemplate;

    public OrderServiceImpl(OrderRepository orderRepository, JdbcTemplate jdbcTemplate) {
        this.orderRepository = orderRepository;
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<Order> findOrders(String status) {
        return orderRepository.findByStatus(status);
    }

    public void createOrder(OrderRequest r) {
        if (r.getQuantity() <= 0) {
            throw new IllegalArgumentException("Quantity must be at least 1");
        }
        orderRepository.save(new Order(r));
        jdbcTemplate.update("INSERT INTO order_audit (order_ref, action) VALUES (?, 'CREATE')", r.getRef());
        jdbcTemplate.execute("{call sp_recalc_stock(?)}");
    }
}
