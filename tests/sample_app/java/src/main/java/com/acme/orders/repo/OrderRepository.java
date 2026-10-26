package com.acme.orders.repo;
public interface OrderRepository extends JpaRepository<Order, Long> {
    List<Order> findByStatus(String status);
    @Query("SELECT o FROM Order o WHERE o.customer = ?1")
    List<Order> findForCustomer(String c);
}
