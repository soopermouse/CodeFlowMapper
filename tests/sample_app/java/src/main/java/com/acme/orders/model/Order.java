package com.acme.orders.model;
@Entity
@Table(name = "ORDERS")
public class Order {
    @Id private Long id;
    private String status;
}
