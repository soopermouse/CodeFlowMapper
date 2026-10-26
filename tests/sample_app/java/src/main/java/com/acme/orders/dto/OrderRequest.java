package com.acme.orders.dto;
public class OrderRequest {
    @NotBlank(message = "Reference is required")
    @Size(max = 20)
    private String ref;
    @NotNull(message = "Quantity is required")
    private Integer quantity;
    private Boolean urgent;
}
