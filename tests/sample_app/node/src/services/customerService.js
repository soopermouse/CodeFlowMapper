const db = require('../db');
async function search(name, page) {
  return db.query('SELECT id, name, status FROM customers WHERE name LIKE $1 LIMIT 50 OFFSET $2', [name, page * 50]);
}
async function block(id, reason) {
  await db.query('UPDATE customers SET status = $1 WHERE id = $2', ['BLOCKED', id]);
  await db.query('INSERT INTO customer_events (customer_id, reason) VALUES ($1, $2)', [id, reason]);
}
module.exports = { search, block };
