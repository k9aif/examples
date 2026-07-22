#!/usr/bin/env python3
"""
Storefront server -- category browsing, guest/logged-in checkout, user
portal (register/login/order history), admin portal (all orders +
livestock gate approval).

Not the Router/Storefront API (that's Phase 2, still ahead) -- this is
a small, honest, real backend for the storefront demo: real Postgres
data, real checkout via petstore/services/checkout.py, real password
auth via petstore/services/auth.py, real gate approval via
petstore/gates/. Everything here calls the same deterministic services
and tests already prove work in isolation -- this just gives them an
HTTP front door.
"""

from __future__ import annotations

import asyncio
import html
import os
import secrets
import sys
from http import cookies
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from petstore.gates import GateRegistryFactory, GateType  # noqa: E402
from petstore.services import auth, cart, checkout, fulfillment, inventory  # noqa: E402
from petstore.services.original_catalog_data import (  # noqa: E402
    image_for_species,
    raw_items,
    species_by_category,
)

_SPECIES_BY_CATEGORY = species_by_category()
_RAW_ITEMS = raw_items()

_CATEGORY_TITLES = {
    "FISH": "Fish", "DOGS": "Dogs", "CATS": "Cats",
    "BIRDS": "Birds", "REPTILES": "Reptiles",
}

_USER_COOKIE = "petstore_session"
_ADMIN_COOKIE = "petstore_admin_session"
_CART_COOKIE = "petstore_cart"


# ── Page chrome ──────────────────────────────────────────────────────────

_STYLE = """
  * { box-sizing: border-box; }
  body { margin: 0; font-family: Verdana, Arial, Helvetica, sans-serif; font-size: 13px; color: #000; background: #fff; }
  .topbar { background: #163832 url('images/bkg-topbar.gif') repeat-x; color: #fff; padding: 8px 14px;
            display: flex; justify-content: space-between; align-items: center; }
  .topbar a, .topbar span { color: #fff; text-decoration: none; margin-left: 16px; }
  .topbar a:hover { text-decoration: underline; }
  .topbar .cart-link { background: rgba(255,255,255,0.15); padding: 4px 10px; border-radius: 4px; }
  .content { padding: 28px; max-width: 720px; margin: 0 auto; }
  h1 { color: #163832; font-family: Georgia, serif; margin-top: 0; }
  h2 { color: #163832; font-family: Georgia, serif; font-size: 16px; }
  table { width: 100%; border-collapse: collapse; margin-top: 16px; }
  th, td { text-align: left; padding: 8px; border-bottom: 1px solid #ddd; font-size: 12px; }
  th { background: #eef3f8; color: #163832; }
  .back { display: inline-block; margin-top: 20px; color: #163832; }
  .empty { color: #777; font-style: italic; margin-top: 16px; }
  .card { background: #fafcfe; border: 1px solid #d9e4ec; border-radius: 6px; padding: 20px; max-width: 380px; margin-top: 16px; }
  .card label { display: block; margin-top: 12px; font-size: 12px; color: #163832; font-weight: bold; }
  .card input, .card select { width: 100%; padding: 6px; font-size: 13px; margin-top: 4px; border: 1px solid #ccc; border-radius: 3px; }
  .card button, .btn { margin-top: 18px; background: #163832; color: #fff; border: none; padding: 9px 16px;
                         border-radius: 4px; font-size: 13px; cursor: pointer; }
  .card button:hover, .btn:hover { background: #0e2622; }
  .error { background: #fdecea; color: #a33; border: 1px solid #f5c6cb; border-radius: 4px; padding: 10px; margin-top: 14px; font-size: 12px; }
  .success { background: #eafaf0; color: #1a6b3c; border: 1px solid #b6e6c9; border-radius: 4px; padding: 14px; margin-top: 14px; font-size: 13px; }
  .pending { background: #fff8e6; color: #8a6d1a; border: 1px solid #f0dca0; border-radius: 4px; padding: 14px; margin-top: 14px; font-size: 13px; }
  .muted { color: #777; font-size: 12px; }
  .state-badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; }
  .state-created, .state-payment_authorized { background: #eef3f8; color: #163832; }
  .state-fulfilling { background: #fff8e6; color: #8a6d1a; }
  .state-shipped, .state-delivered { background: #eafaf0; color: #1a6b3c; }
  .state-cancelled { background: #fdecea; color: #a33; }
  form.inline { display: inline; }
"""


def _page(title: str, body_html: str, nav_html: str = "") -> bytes:
    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Pet Store Agentic — {html.escape(title)}</title>
<style>{_STYLE}</style>
</head>
<body>
  <div class="topbar">
    <a href="index.html">&larr; Pet Store Agentic</a>
    <div>{nav_html}</div>
  </div>
  <div class="content">
    <h1>{html.escape(title)}</h1>
    {body_html}
  </div>
</body>
</html>"""
    return doc.encode("utf-8")


def _nav(user: Optional[dict], admin_principal: Optional[Tuple[str, str]], cart_count: int = 0) -> str:
    cart_link = f'<a href="/cart" class="cart-link">&#128722; Cart ({cart_count})</a>'
    if admin_principal:
        return '<a href="/admin">Admin Dashboard</a><a href="/admin/logout">Admin Logout</a>'
    if user:
        return (f'{cart_link}<span>Logged in as: {html.escape(user["name"])}</span>'
                f'<a href="/orders">My Orders</a><a href="/logout">Logout</a>')
    return (f'{cart_link}<a href="/login">Login</a><a href="/register">Register</a>'
            f'<a href="/admin/login">Admin</a>')


# ── Category browsing (existing) ────────────────────────────────────────

def _render_category(category_id: str, nav_html: str) -> bytes:
    category_id = (category_id or "").upper()
    title = _CATEGORY_TITLES.get(category_id, category_id or "Unknown category")
    species_set = _SPECIES_BY_CATEGORY.get(category_id, set())

    rows = []
    if species_set:
        for sku_id, species, orig_cat, desc, variant, _price in _RAW_ITEMS:
            if orig_cat != category_id:
                continue
            sku = inventory.get_sku(sku_id)
            if sku is not None:
                rows.append(sku)

    if rows:
        parts = ["<table><tr><th></th><th>SKU</th><th>Name</th><th>Description</th><th>Price</th><th></th></tr>"]
        for sku in rows:
            image_file = image_for_species(sku.species) if sku.species else None
            img_cell = (f'<img src="images/{html.escape(image_file)}" alt="{html.escape(sku.species or "")}" '
                        f'style="width:56px;height:42px;object-fit:cover;border-radius:4px;border:1px solid #ccc">'
                        if image_file else "")
            parts.append(
                f"<tr><td>{img_cell}</td>"
                f"<td>{html.escape(sku.sku_id)}</td>"
                f"<td>{html.escape(sku.name)}</td>"
                f"<td>{html.escape(sku.description)}</td>"
                f"<td>${sku.unit_price_cents / 100:.2f}</td>"
                f'<td><form class="inline" method="post" action="/cart/add">'
                f'<input type="hidden" name="sku_id" value="{html.escape(sku.sku_id)}">'
                f'<button class="btn" style="padding:4px 10px;font-size:11px" type="submit">'
                f'Add to Cart</button></form></td></tr>'
            )
        parts.append("</table>")
        body = "".join(parts)
    else:
        body = ('<p class="empty">No items found for this category (or the catalog hasn\'t been '
                'seeded yet -- run demo/seed_original_catalog.py).</p>')

    body += '<a class="back" href="index.html">&larr; Back to storefront</a>'
    return _page(title, body, nav_html)


# ── Auth pages ───────────────────────────────────────────────────────────

def _login_page(error: Optional[str] = None, cart_count: int = 0) -> bytes:
    err = f'<div class="error">{html.escape(error)}</div>' if error else ""
    body = f"""
    <div class="card">
      <form method="post" action="/login">
        <label>Email</label>
        <input type="text" name="email" required>
        <label>Password</label>
        <input type="password" name="password" required>
        <button type="submit">Log In</button>
      </form>
      {err}
      <p class="muted">Try <strong>demo</strong> / <strong>demo</strong> to see an account with sample order history already in it.</p>
      <p class="muted">No account? <a href="/register">Register here</a>.</p>
    </div>
    """
    return _page("Log In", body, _nav(None, None, cart_count))


def _register_page(error: Optional[str] = None, cart_count: int = 0) -> bytes:
    err = f'<div class="error">{html.escape(error)}</div>' if error else ""
    body = f"""
    <div class="card">
      <form method="post" action="/register">
        <label>Name</label>
        <input type="text" name="name" required>
        <label>Email</label>
        <input type="text" name="email" required>
        <label>Password</label>
        <input type="password" name="password" required minlength="6">
        <button type="submit">Create Account</button>
      </form>
      {err}
      <p class="muted">Already have an account? <a href="/login">Log in</a>.</p>
    </div>
    """
    return _page("Register", body, _nav(None, None, cart_count))


def _admin_login_page(error: Optional[str] = None) -> bytes:
    err = f'<div class="error">{html.escape(error)}</div>' if error else ""
    body = f"""
    <div class="card">
      <form method="post" action="/admin/login">
        <label>Username</label>
        <input type="text" name="username" required>
        <label>Password</label>
        <input type="password" name="password" required>
        <button type="submit">Admin Log In</button>
      </form>
      {err}
      <p class="muted">Admin accounts are provisioned via demo/seed_admin.py, not self-registered.</p>
    </div>
    """
    return _page("Admin Login", body, "")


# ── Cart ─────────────────────────────────────────────────────────────────

def _cart_page(cart_session_id: Optional[str], user: Optional[dict]) -> bytes:
    lines = cart.get_cart(cart_session_id) if cart_session_id else []

    if not lines:
        body = ('<p class="empty">Your cart is empty.</p>'
                '<a class="back" href="index.html">&larr; Continue shopping</a>')
        return _page("Your Cart", body, _nav(user, None, 0))

    rows = ["<table><tr><th></th><th>Item</th><th>Price</th><th>Qty</th><th>Subtotal</th><th></th></tr>"]
    total = 0
    for line in lines:
        image_file = image_for_species(line.sku.species) if line.sku.species else None
        img_cell = (f'<img src="images/{html.escape(image_file)}" alt="" '
                    f'style="width:48px;height:36px;object-fit:cover;border-radius:4px;border:1px solid #ccc">'
                    if image_file else "")
        total += line.subtotal_cents
        rows.append(
            f"<tr><td>{img_cell}</td><td>{html.escape(line.sku.name)}</td>"
            f"<td>${line.sku.unit_price_cents / 100:.2f}</td>"
            f"<td>"
            f'<form class="inline" method="post" action="/cart/update">'
            f'<input type="hidden" name="sku_id" value="{html.escape(line.sku.sku_id)}">'
            f'<input type="number" name="quantity" value="{line.quantity}" min="1" '
            f'style="width:50px" onchange="this.form.submit()">'
            f"</form></td>"
            f"<td>${line.subtotal_cents / 100:.2f}</td>"
            f"<td>"
            f'<form class="inline" method="post" action="/cart/remove">'
            f'<input type="hidden" name="sku_id" value="{html.escape(line.sku.sku_id)}">'
            f'<button class="btn" style="padding:3px 10px;font-size:11px;background:#a33" '
            f'type="submit">Remove</button></form>'
            f"</td></tr>"
        )
    rows.append(f"<tr><td colspan='4' style='text-align:right'><strong>Total</strong></td>"
                f"<td colspan='2'><strong>${total / 100:.2f}</strong></td></tr>")
    rows.append("</table>")

    body = "".join(rows)
    body += '<a class="btn" href="/checkout" style="display:inline-block;text-decoration:none;margin-top:20px">Proceed to Checkout</a>'
    body += ' <a class="back" href="index.html">&larr; Continue shopping</a>'
    return _page("Your Cart", body, _nav(user, None, cart.get_item_count(cart_session_id)))


# ── Checkout ─────────────────────────────────────────────────────────────

def _checkout_page(cart_session_id: Optional[str], user: Optional[dict], error: Optional[str] = None) -> bytes:
    lines = cart.get_cart(cart_session_id) if cart_session_id else []
    if not lines:
        body = ('<p class="empty">Your cart is empty -- add something first.</p>'
                '<a class="back" href="index.html">&larr; Continue shopping</a>')
        return _page("Checkout", body, _nav(user, None, 0))

    err = f'<div class="error">{html.escape(error)}</div>' if error else ""
    guest_note = "" if user else '<p class="muted">Checking out as a guest -- no account needed.</p>'
    has_livestock = any(line.sku.is_livestock for line in lines)
    gate_note = ('<p class="muted"><strong>Note:</strong> this order contains livestock -- it will '
                 "wait for admin approval before shipping.</p>" if has_livestock else "")

    summary_rows = []
    total = 0
    for line in lines:
        total += line.subtotal_cents
        summary_rows.append(
            f"<tr><td>{html.escape(line.sku.name)} &times; {line.quantity}</td>"
            f"<td>${line.subtotal_cents / 100:.2f}</td></tr>"
        )
    summary_rows.append(f"<tr><td><strong>Total</strong></td><td><strong>${total / 100:.2f}</strong></td></tr>")

    body = f"""
    <table>{"".join(summary_rows)}</table>
    <div class="card">
      {guest_note}
      {gate_note}
      <form method="post" action="/checkout">
        {'' if user else '<label>Your name (guest checkout)</label><input type="text" name="guest_name" required>'}
        <label>Card number (any value ending in 0000 is declined, for testing)</label>
        <input type="text" name="payment_method" value="4111-1111-1111-1234" required>
        <button type="submit">Place Order</button>
      </form>
      {err}
    </div>
    """
    return _page("Checkout", body, _nav(user, None, cart.get_item_count(cart_session_id)))


def _order_confirmation_page(result, user: Optional[dict], cart_count: int = 0) -> bytes:
    if not result.success:
        body = f'<div class="error">Order {html.escape(result.order_id)} could not be placed: {html.escape(result.reason or "unknown reason")}</div>'
    elif result.awaiting_gate_approval:
        body = f"""
        <div class="pending">
          Order <strong>{html.escape(result.order_id)}</strong> placed -- total ${result.total_cents / 100:.2f}.<br>
          This order contains livestock and is waiting for admin approval before it ships.
        </div>
        <p class="muted">Track this order any time at
          <a href="/order-status?order_id={html.escape(result.order_id)}">/order-status?order_id={html.escape(result.order_id)}</a></p>
        """
    else:
        body = f"""
        <div class="success">
          Order <strong>{html.escape(result.order_id)}</strong> placed and shipped -- total ${result.total_cents / 100:.2f}.
        </div>
        <p class="muted">Track this order any time at
          <a href="/order-status?order_id={html.escape(result.order_id)}">/order-status?order_id={html.escape(result.order_id)}</a></p>
        """
    if user:
        body += '<p><a href="/orders">View my order history &rarr;</a></p>'
    body += '<a class="back" href="index.html">&larr; Back to storefront</a>'
    return _page("Order Confirmation", body, _nav(user, None, cart_count))


def _order_status_page(order_id: str, user: Optional[dict], cart_count: int = 0) -> bytes:
    status = fulfillment.get_order_status(order_id) if order_id else None
    if status is None:
        body = '<p class="empty">No order found with that ID.</p>'
    else:
        body = f"""
        <table>
          <tr><th>Order ID</th><td>{html.escape(status['order_id'])}</td></tr>
          <tr><th>Status</th><td><span class="state-badge state-{status['state']}">{status['state']}</span></td></tr>
          <tr><th>Total</th><td>${status['total_cents'] / 100:.2f}</td></tr>
          <tr><th>Placed</th><td>{status['created_at']}</td></tr>
          <tr><th>Updated</th><td>{status['updated_at']}</td></tr>
        </table>
        """
    body += '<a class="back" href="index.html">&larr; Back to storefront</a>'
    return _page("Order Status", body, _nav(user, None, cart_count))


def _orders_page(user: dict, cart_count: int = 0) -> bytes:
    history = fulfillment.get_order_history_for_user(user["user_id"])
    if not history:
        body = '<p class="empty">No orders yet.</p>'
    else:
        rows = ["<table><tr><th>Order ID</th><th>Status</th><th>Total</th><th>Placed</th></tr>"]
        for o in history:
            rows.append(
                f"<tr><td><a href=\"/order-status?order_id={html.escape(o['order_id'])}\">{html.escape(o['order_id'][:8])}...</a></td>"
                f"<td><span class=\"state-badge state-{o['state']}\">{o['state']}</span></td>"
                f"<td>${o['total_cents'] / 100:.2f}</td><td>{o['created_at']}</td></tr>"
            )
        rows.append("</table>")
        body = "".join(rows)
    return _page("My Orders", body, _nav(user, None, cart_count))


# ── Admin portal ─────────────────────────────────────────────────────────

def _admin_dashboard_page() -> bytes:
    registry = GateRegistryFactory.create({})
    pending_gates = asyncio.run(registry.list_pending(GateType.LIVESTOCK))
    all_orders = fulfillment.get_all_orders()

    gate_rows = ["<h2>Pending Livestock Gates</h2>"]
    if pending_gates:
        gate_rows.append("<table><tr><th>Gate ID</th><th>Order ID</th><th>Created</th><th>Action</th></tr>")
        for g in pending_gates:
            gate_rows.append(
                f"<tr><td>{html.escape(g.gate_id[:8])}...</td>"
                f"<td><a href=\"/order-status?order_id={html.escape(g.order_id)}\">{html.escape(g.order_id[:8])}...</a></td>"
                f"<td>{g.created_at}</td>"
                f"<td>"
                f'<form class="inline" method="post" action="/admin/gate/resolve">'
                f'<input type="hidden" name="gate_id" value="{html.escape(g.gate_id)}">'
                f'<input type="hidden" name="decision" value="approve">'
                f'<button class="btn" style="padding:3px 10px;font-size:11px" type="submit">Approve</button></form> '
                f'<form class="inline" method="post" action="/admin/gate/resolve">'
                f'<input type="hidden" name="gate_id" value="{html.escape(g.gate_id)}">'
                f'<input type="hidden" name="decision" value="reject">'
                f'<button class="btn" style="padding:3px 10px;font-size:11px;background:#a33" type="submit">Reject</button></form>'
                f"</td></tr>"
            )
        gate_rows.append("</table>")
    else:
        gate_rows.append('<p class="empty">No pending livestock gates.</p>')

    order_rows = ['<h2 style="margin-top:32px">All Orders</h2>',
                  "<table><tr><th>Order ID</th><th>Customer</th><th>Status</th><th>Total</th><th>Placed</th></tr>"]
    for o in all_orders[:50]:
        order_rows.append(
            f"<tr><td>{html.escape(o['order_id'][:8])}...</td><td>{html.escape(o['customer_id'])}</td>"
            f"<td><span class=\"state-badge state-{o['state']}\">{o['state']}</span></td>"
            f"<td>${o['total_cents'] / 100:.2f}</td><td>{o['created_at']}</td></tr>"
        )
    order_rows.append("</table>")

    body = "".join(gate_rows) + "".join(order_rows)
    return _page("Admin Dashboard", body, '<a href="/admin/logout">Admin Logout</a>')


# ── Request handling ─────────────────────────────────────────────────────

def _get_cookie(handler: SimpleHTTPRequestHandler, name: str) -> Optional[str]:
    raw = handler.headers.get("Cookie")
    if not raw:
        return None
    jar = cookies.SimpleCookie()
    jar.load(raw)
    morsel = jar.get(name)
    return morsel.value if morsel else None


def _current_user(handler: SimpleHTTPRequestHandler) -> Optional[dict]:
    token = _get_cookie(handler, _USER_COOKIE)
    if not token:
        return None
    principal = auth.get_session(token)
    if principal is None or principal[0] != "user":
        return None
    return auth.get_user(principal[1])


def _current_admin(handler: SimpleHTTPRequestHandler) -> Optional[Tuple[str, str]]:
    token = _get_cookie(handler, _ADMIN_COOKIE)
    if not token:
        return None
    principal = auth.get_session(token)
    if principal is None or principal[0] != "admin":
        return None
    return principal


def _current_cart_session(handler: SimpleHTTPRequestHandler) -> Optional[str]:
    """Read-only -- returns None if no cart cookie exists yet (an empty cart)."""
    return _get_cookie(handler, _CART_COOKIE)


def _parse_form(handler: SimpleHTTPRequestHandler) -> Dict[str, str]:
    length = int(handler.headers.get("Content-Length", 0))
    raw = handler.rfile.read(length).decode("utf-8")
    parsed = parse_qs(raw)
    return {k: v[0] for k, v in parsed.items()}


class Handler(SimpleHTTPRequestHandler):

    def _send_html(self, body: bytes, status: int = 200, set_cookie: Optional[str] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str, set_cookie: Optional[str] = None) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        self.end_headers()

    # ── GET ──────────────────────────────────────────────────────────
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        user = _current_user(self)
        admin = _current_admin(self)
        cart_session_id = _current_cart_session(self)
        cart_count = cart.get_item_count(cart_session_id) if cart_session_id else 0

        if path == "/category":
            self._send_html(_render_category(query.get("category_id", [""])[0], _nav(user, admin, cart_count)))
            return
        if path == "/login":
            self._send_html(_login_page(cart_count=cart_count))
            return
        if path == "/register":
            self._send_html(_register_page(cart_count=cart_count))
            return
        if path == "/logout":
            token = _get_cookie(self, _USER_COOKIE)
            if token:
                auth.logout(token)
            self._redirect("/index.html", set_cookie=f"{_USER_COOKIE}=; Path=/; Max-Age=0")
            return
        if path == "/cart":
            self._send_html(_cart_page(cart_session_id, user))
            return
        if path == "/checkout":
            self._send_html(_checkout_page(cart_session_id, user))
            return
        if path == "/orders":
            if not user:
                self._redirect("/login")
                return
            self._send_html(_orders_page(user, cart_count))
            return
        if path == "/order-status":
            self._send_html(_order_status_page(query.get("order_id", [""])[0], user, cart_count))
            return
        if path == "/admin/login":
            self._send_html(_admin_login_page())
            return
        if path == "/admin/logout":
            token = _get_cookie(self, _ADMIN_COOKIE)
            if token:
                auth.logout(token)
            self._redirect("/index.html", set_cookie=f"{_ADMIN_COOKIE}=; Path=/; Max-Age=0")
            return
        if path == "/admin":
            if not admin:
                self._redirect("/admin/login")
                return
            self._send_html(_admin_dashboard_page())
            return

        super().do_GET()

    # ── POST ─────────────────────────────────────────────────────────
    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        form = _parse_form(self)
        _cart_session_for_nav = _current_cart_session(self)
        cart_count = cart.get_item_count(_cart_session_for_nav) if _cart_session_for_nav else 0

        if path == "/login":
            token = auth.login_user(form.get("email", ""), form.get("password", ""))
            if token is None:
                self._send_html(_login_page(error="Invalid email or password.", cart_count=cart_count), status=401)
                return
            self._redirect("/orders", set_cookie=f"{_USER_COOKIE}={token}; Path=/; HttpOnly")
            return

        if path == "/register":
            try:
                auth.register_user(form.get("email", ""), form.get("password", ""), form.get("name", ""))
            except ValueError as exc:
                self._send_html(_register_page(error=str(exc), cart_count=cart_count), status=400)
                return
            token = auth.login_user(form["email"], form["password"])
            # Register -> home page (a brand-new account has no orders yet,
            # so /orders would just be an empty page); Login -> /orders
            # (a returning user checking status is the more useful default).
            self._redirect("/index.html", set_cookie=f"{_USER_COOKIE}={token}; Path=/; HttpOnly")
            return

        if path == "/admin/login":
            token = auth.login_admin(form.get("username", ""), form.get("password", ""))
            if token is None:
                self._send_html(_admin_login_page(error="Invalid username or password."), status=401)
                return
            self._redirect("/admin", set_cookie=f"{_ADMIN_COOKIE}={token}; Path=/; HttpOnly")
            return

        if path == "/cart/add":
            cart_session_id = _current_cart_session(self)
            new_cookie = None
            if cart_session_id is None:
                cart_session_id = secrets.token_urlsafe(16)
                new_cookie = f"{_CART_COOKIE}={cart_session_id}; Path=/; HttpOnly"
            cart.add_item(cart_session_id, form.get("sku_id", ""), max(1, int(form.get("quantity", "1") or 1)))
            self._redirect("/cart", set_cookie=new_cookie)
            return

        if path == "/cart/remove":
            cart_session_id = _current_cart_session(self)
            if cart_session_id:
                cart.remove_item(cart_session_id, form.get("sku_id", ""))
            self._redirect("/cart")
            return

        if path == "/cart/update":
            cart_session_id = _current_cart_session(self)
            if cart_session_id:
                try:
                    quantity = int(form.get("quantity", "1"))
                except ValueError:
                    quantity = 1
                cart.update_quantity(cart_session_id, form.get("sku_id", ""), quantity)
            self._redirect("/cart")
            return

        if path == "/checkout":
            user = _current_user(self)
            cart_session_id = _current_cart_session(self)
            cart_lines = cart.as_checkout_items(cart_session_id) if cart_session_id else []
            if not cart_lines:
                self._redirect("/cart")
                return
            customer_id = user["email"] if user else form.get("guest_name", "guest")
            result = checkout.place_order(
                cart=cart_lines,
                customer_id=customer_id,
                payment_method=form.get("payment_method", ""),
                user_id=user["user_id"] if user else None,
            )
            if result.success:
                cart.clear_cart(cart_session_id)
            self._send_html(_order_confirmation_page(result, user, cart.get_item_count(cart_session_id)))
            return

        if path == "/admin/gate/resolve":
            admin = _current_admin(self)
            if not admin:
                self._redirect("/admin/login")
                return
            registry = GateRegistryFactory.create({})
            approved = form.get("decision") == "approve"
            gate = asyncio.run(registry.resolve(form["gate_id"], approved=approved, approver=admin[1]))
            if approved:
                checkout.complete_after_gate_approval(gate.order_id)
            else:
                checkout.cancel_after_gate_rejection(gate.order_id)
            self._redirect("/admin")
            return

        self.send_response(404)
        self.end_headers()


def main() -> None:
    port = int(os.environ.get("PETSTORE_WEBUI_PORT", "8500"))
    os.chdir(Path(__file__).resolve().parent)
    server = HTTPServer(("", port), Handler)
    print(f"Serving storefront (category browsing, checkout, accounts, admin) on http://localhost:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
