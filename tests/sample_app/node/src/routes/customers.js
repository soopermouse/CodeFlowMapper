const express = require('express');
const router = express.Router();
const customerService = require('../services/customerService');
const { requireAuth } = require('../auth');

router.get('/api/customers', requireAuth, async (req, res) => {
  const { name, page } = req.query;
  const rows = await customerService.search(name, page);
  res.json(rows);
});

router.post('/api/customers/:id/block', requireAuth, async (req, res) => {
  if (!req.body.reason) {
    return res.status(400).json({ error: 'A reason is required to block a customer' });
  }
  await customerService.block(req.params.id, req.body.reason);
  res.json({ ok: true });
});

module.exports = router;
