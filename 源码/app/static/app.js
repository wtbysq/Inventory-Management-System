/* 库存管理系统前端脚本
 *
 * 结构:
 *   1. 全局状态与工具函数
 *   2. 登录 / 权限
 *   3. 商品与库存
 *   4. 订单（支付 / 取消 / 退货）
 *   5. 任务
 *   6. 盘点
 *   7. 调拨与仓库
 *   8. 用户管理
 *   9. 事件绑定与入口
 */

const ROLE_LABELS = {
  admin: "管理员",
  operator: "操作员",
  viewer: "只读用户",
};

const ORDER_STATUS = {
  CREATED: "已创建",
  PAID: "已支付",
  CANCELLED: "已取消",
  PARTIALLY_RETURNED: "部分退货",
  RETURNED: "已退货",
};

const TASK_STATUS = {
  PENDING: "待处理",
  IN_PROGRESS: "进行中",
  DONE: "已完成",
  CANCELLED: "已取消",
};

const PRIORITY_LABELS = {
  LOW: "低",
  NORMAL: "普通",
  HIGH: "高",
  URGENT: "紧急",
};

const STOCKTAKE_STATUS = {
  COUNTING: "盘点中",
  CONFIRMED: "已确认",
  CANCELLED: "已取消",
};

const state = {
  token: localStorage.getItem("inv_token") || "",
  user: JSON.parse(localStorage.getItem("inv_user") || "null"),
  tab: "products",
  categories: new Map(),
  allProducts: [],
  allProductsLoaded: false,
  products: {
    page: 1,
    size: 20,
    total: 0,
    keyword: "",
    categoryId: "",
    lowStockOnly: false,
    items: [],
  },
  orders: { page: 1, size: 20, total: 0, status: "", items: [] },
  tasks: { page: 1, size: 20, total: 0, status: "", items: [] },
  stocktakes: { page: 1, size: 20, total: 0, items: [] },
  transfers: { page: 1, size: 20, total: 0, items: [] },
  warehouses: [],
  orderItems: [],
  orderProductId: null,
  orderProductMatches: [],
  orderProductActive: -1,
  transferItems: [],
  returnOrder: null,
  countStocktake: null,
};

const $ = (id) => document.getElementById(id);
let toastTimer = null;

/* ------------------------------------------------------------------ *
 * 1. 工具函数
 * ------------------------------------------------------------------ */
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));
}

function formatMoney(value) {
  const number = Number(value ?? 0);
  if (!Number.isFinite(number)) return "¥0.00";
  return `¥${number.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value).replace("T", " ").slice(0, 19);
  }
  return date.toLocaleString("zh-CN", { hour12: false });
}

function trimOrNull(value) {
  const text = String(value ?? "").trim();
  return text || null;
}

function toast(message, type = "success") {
  const element = $("toast");
  element.textContent = message;
  element.className = `toast ${type === "error" ? "error" : ""}`.trim();
  element.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    element.hidden = true;
  }, 3400);
}

function showError(error) {
  toast(error?.message || "操作失败，请稍后重试", "error");
}

function closeModal(id) {
  const element = $(id);
  if (element) element.hidden = true;
}

function badge(className, text) {
  return `<span class="badge ${className}">${escapeHtml(text)}</span>`;
}

// 各业务状态对应的徽章样式，渲染时按状态查表，避免重复写三份映射。
const BADGE_STYLE = {
  order: {
    CREATED: "badge-info",
    PAID: "badge-ok",
    CANCELLED: "badge-muted",
    PARTIALLY_RETURNED: "badge-warn",
    RETURNED: "badge-low",
  },
  task: {
    PENDING: "badge-info",
    IN_PROGRESS: "badge-warn",
    DONE: "badge-ok",
    CANCELLED: "badge-muted",
  },
  stocktake: {
    COUNTING: "badge-warn",
    CONFIRMED: "badge-ok",
    CANCELLED: "badge-muted",
  },
};

function statusBadge(kind, status, labels) {
  return badge(BADGE_STYLE[kind][status] || "badge-muted", labels[status] || status);
}

function orderBadge(status) {
  return statusBadge("order", status, ORDER_STATUS);
}

function taskBadge(status) {
  return statusBadge("task", status, TASK_STATUS);
}

function stocktakeBadge(status) {
  return statusBadge("stocktake", status, STOCKTAKE_STATUS);
}

/* ------------------------------------------------------------------ *
 * 2. 请求封装与登录
 * ------------------------------------------------------------------ */
async function api(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  if (state.token) {
    headers.Authorization = `Bearer ${state.token}`;
  }

  const response = await fetch(path, { ...options, headers });

  let data = null;
  try {
    data = await response.json();
  } catch (_error) {
    data = null;
  }

  if (response.status === 401) {
    handleUnauthorized(data?.message);
    throw new Error(data?.message || "登录已过期，请重新登录");
  }

  if (!response.ok) {
    throw new Error(data?.message || `请求失败（${response.status}）`);
  }
  return data;
}

function persistAuth() {
  if (state.token) {
    localStorage.setItem("inv_token", state.token);
    localStorage.setItem("inv_user", JSON.stringify(state.user || {}));
  } else {
    localStorage.removeItem("inv_token");
    localStorage.removeItem("inv_user");
  }
}

function handleUnauthorized(message) {
  state.token = "";
  state.user = null;
  persistAuth();
  $("loginLayer").hidden = false;
  if (message) toast(message, "error");
}

function isAdmin() {
  return state.user?.role === "admin";
}

function canWrite() {
  return Boolean(state.user) && state.user.role !== "viewer";
}

function applyAuthUi() {
  const user = state.user || {};
  $("userName").textContent = user.full_name || user.username || "未登录";
  $("currentUserRole").textContent = ROLE_LABELS[user.role] || "-";
  $("userAvatar").textContent = (user.username || "-").slice(0, 1).toUpperCase();

  // 仅管理员可见的标签页 / 按钮。
  document.querySelectorAll("[data-admin-only]").forEach((element) => {
    element.hidden = !isAdmin();
  });
  // 只读用户隐藏所有写操作按钮。
  document.querySelectorAll("[data-write]").forEach((element) => {
    element.hidden = !canWrite();
  });
}

async function login(username, password) {
  const response = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(data?.message || "登录失败");
  }

  state.token = data.access_token;
  state.user = data.user;
  persistAuth();
  $("loginLayer").hidden = true;
  await startApp();
}

/* ------------------------------------------------------------------ *
 * 3. 商品与库存
 * ------------------------------------------------------------------ */
async function loadCategories() {
  const categories = await api("/api/categories");
  state.categories = new Map(
    categories.map((category) => [String(category.id), category.category_name]),
  );

  const options = [
    '<option value="">全部分类</option>',
    ...categories.map(
      (category) =>
        `<option value="${category.id}">${escapeHtml(category.category_name)}</option>`,
    ),
  ].join("");

  $("categorySelect").innerHTML = options;
  $("stocktakeCategory").innerHTML = [
    '<option value="">全部分类</option>',
    ...categories.map(
      (category) =>
        `<option value="${category.id}">${escapeHtml(category.category_name)}</option>`,
    ),
  ].join("");
}

async function loadStats() {
  const stats = await api("/api/products/stats");
  $("statProducts").textContent = stats.total_products;
  $("statQuantity").textContent = stats.total_quantity;
  $("statValue").textContent = formatMoney(stats.total_inventory_value);
  $("statLowStock").textContent = stats.low_stock_count;
}

async function loadOrderStats() {
  const stats = await api("/api/orders/stats");
  $("statProfit").textContent = formatMoney(stats.total_profit);
  $("statProfit").className = Number(stats.total_profit) < 0 ? "money-neg" : "";
  $("statRevenue").textContent = formatMoney(stats.total_revenue);
  $("statPaidOrders").textContent = String(stats.paid_order_count ?? 0);
}

async function loadProducts() {
  const params = new URLSearchParams({
    page: String(state.products.page),
    size: String(state.products.size),
  });
  if (state.products.keyword) params.set("keyword", state.products.keyword);
  if (state.products.categoryId) params.set("category_id", state.products.categoryId);
  if (state.products.lowStockOnly) params.set("low_stock_only", "true");

  const data = await api(`/api/products?${params.toString()}`);
  state.products.items = data.items;
  state.products.total = data.total;
  renderProducts();
  renderPager();
}

function renderProducts() {
  const tbody = $("productTableBody");
  const emptyState = $("emptyState");
  $("resultCount").textContent = `共 ${state.products.total} 条`;

  if (!state.products.items.length) {
    tbody.innerHTML = "";
    emptyState.hidden = false;
    return;
  }

  emptyState.hidden = true;
  const writable = canWrite();

  tbody.innerHTML = state.products.items.map((product) => {
    const isLow = product.quantity < product.low_stock_threshold;
    const categoryName = state.categories.get(String(product.category_id))
      || `分类 ${product.category_id}`;

    return `
      <tr>
        <td class="product-cell">
          <span class="product-name">${escapeHtml(product.product_name)}</span>
          <span class="product-meta">ID: ${product.id} · 阈值 ${product.low_stock_threshold}</span>
        </td>
        <td><span class="sku">${escapeHtml(product.sku)}</span></td>
        <td>${escapeHtml(categoryName)}</td>
        <td class="num"><strong>${product.quantity}</strong></td>
        <td class="num">${formatMoney(product.price)}</td>
        <td class="num">${product.cost == null ? "-" : formatMoney(product.cost)}</td>
        <td>${badge(isLow ? "badge-low" : "badge-ok", isLow ? "库存偏低" : "正常")}</td>
        <td>${formatDate(product.last_inbound_at)}</td>
        <td>
          <div class="row-actions">
            ${writable ? `
              <button class="mini-btn" type="button" data-action="in" data-id="${product.id}">入库</button>
              <button class="mini-btn danger" type="button" data-action="out" data-id="${product.id}">出库</button>
            ` : '<span class="muted-text">只读</span>'}
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

/* 分页器：商品/订单/任务/盘点/调拨共用一套渲染与翻页绑定 */

// 页码按钮最多显示几个（超出用省略号折叠中间的页）。
const PAGER_BUTTON_LIMIT = 9;

function pagerIds(prefix) {
  if (!prefix) {
    return {
      info: "pageInfo",
      prev: "prevPage",
      next: "nextPage",
      numbers: "pageNumbers",
    };
  }
  return {
    info: `${prefix}PageInfo`,
    prev: `${prefix}PrevPage`,
    next: `${prefix}NextPage`,
    numbers: `${prefix}PageNumbers`,
  };
}

function buildPagerItems(current, total) {
  // 页数不多时全部展示，例如 1 2 3 4 5。
  if (total <= PAGER_BUTTON_LIMIT) {
    return Array.from({ length: total }, (_, index) => index + 1);
  }

  // 始终保留首页与末页，中间按当前页展开，其余用省略号。
  let left = Math.max(2, current - 2);
  let right = Math.min(total - 1, current + 2);

  // 靠近两端时补足按钮数量，避免只剩两三个页码。
  if (current <= 4) {
    left = 2;
    right = Math.min(total - 1, PAGER_BUTTON_LIMIT - 2);
  } else if (current >= total - 3) {
    left = Math.max(2, total - (PAGER_BUTTON_LIMIT - 2));
    right = total - 1;
  }

  const items = [1];
  if (left > 2) items.push("…");
  for (let page = left; page <= right; page += 1) items.push(page);
  if (right < total - 1) items.push("…");
  items.push(total);
  return items;
}

function renderPagerNumbers(prefix, stateKey) {
  const container = $(pagerIds(prefix).numbers);
  if (!container) return;

  const pageState = state[stateKey];
  const totalPages = Math.max(1, Math.ceil(pageState.total / pageState.size));

  container.innerHTML = buildPagerItems(pageState.page, totalPages)
    .map((item) => {
      if (item === "…") {
        return '<span class="pager-ellipsis">…</span>';
      }
      if (item === pageState.page) {
        return `<button class="pager-num active" type="button" aria-current="page">${item}</button>`;
      }
      return `<button class="pager-num" type="button" data-page="${item}">${item}</button>`;
    })
    .join("");
}

function renderPagerCore(prefix, stateKey, unit = "条") {
  const pageState = state[stateKey];
  const totalPages = Math.max(1, Math.ceil(pageState.total / pageState.size));
  const ids = pagerIds(prefix);

  $(ids.info).textContent =
    `第 ${pageState.page} / ${totalPages} 页 · 共 ${pageState.total} ${unit}`;
  $(ids.prev).disabled = pageState.page <= 1;
  $(ids.next).disabled = pageState.page >= totalPages;

  renderPagerNumbers(prefix, stateKey);
}

function bindPager(prefix, stateKey, load) {
  const ids = pagerIds(prefix);
  const pageState = () => state[stateKey];
  const totalPages = () => Math.max(
    1,
    Math.ceil(pageState().total / pageState().size),
  );

  $(ids.prev).addEventListener("click", () => {
    if (pageState().page <= 1) return;
    pageState().page -= 1;
    load().catch(showError);
  });

  $(ids.next).addEventListener("click", () => {
    if (pageState().page >= totalPages()) return;
    pageState().page += 1;
    load().catch(showError);
  });

  // 页码按钮用事件委托，翻页后重新渲染也不必重复绑定。
  const numbers = $(ids.numbers);
  if (numbers) {
    numbers.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-page]");
      if (!button) return;

      const target = Number(button.dataset.page);
      if (!Number.isInteger(target) || target < 1 || target > totalPages()) return;
      if (target === pageState().page) return;

      pageState().page = target;
      load().catch(showError);
    });
  }
}

function renderPager() {
  renderPagerCore("", "products", "条");
}

async function refreshStatsAndProducts() {
  await Promise.all([loadStats(), loadOrderStats(), loadProducts()]);
}

function openStockModal(product, type) {
  $("stockProductId").value = product.id;
  $("stockType").value = type;
  $("stockProductName").textContent =
    `${product.product_name} / ${product.sku} · 当前库存 ${product.quantity}`;
  $("stockModalTitle").textContent = type === "in" ? "商品入库" : "商品出库";
  $("stockSubmitBtn").textContent = type === "in" ? "确认入库" : "确认出库";
  $("stockSubmitBtn").className = type === "in" ? "btn btn-primary" : "btn btn-accent";
  $("stockQuantity").value = 1;
  $("stockQuantity").max = type === "out" ? String(product.quantity) : "";
  $("stockOperator").value = "";
  $("stockRemark").value = "";
  $("stockModal").hidden = false;
  $("stockQuantity").focus();
}

async function submitStock(event) {
  event.preventDefault();

  const type = $("stockType").value;
  const payload = {
    product_id: Number($("stockProductId").value),
    quantity: Number($("stockQuantity").value),
    operator: trimOrNull($("stockOperator").value),
    remark: trimOrNull($("stockRemark").value),
  };

  const path = type === "in"
    ? "/api/inventory/inbound"
    : "/api/inventory/outbound";

  try {
    const result = await api(path, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    toast(`${type === "in" ? "入库" : "出库"}成功，当前库存 ${result.after_quantity}`);
    closeModal("stockModal");
    await refreshStatsAndProducts();
    state.allProductsLoaded = false;
  } catch (error) {
    showError(error);
  }
}

// 全量商品加载的进行中 Promise，用于并发去重。
let allProductsPromise = null;

async function fetchAllProducts() {
  // 100 条一页，最多 30 页（3000 条），避免极端数据量把浏览器拖死。
  const MAX_PAGES = 30;
  const products = [];

  const first = await api("/api/products?page=1&size=100");
  products.push(...first.items);

  const totalPages = Math.min(Math.ceil(first.total / 100), MAX_PAGES);
  for (let page = 2; page <= totalPages; page += 1) {
    const data = await api(`/api/products?page=${page}&size=100`);
    products.push(...data.items);
  }

  if (products.length < first.total) {
    toast(`商品较多，仅加载前 ${products.length} 条，可用搜索继续查找`);
  }
  return products;
}

async function ensureAllProducts() {
  if (state.allProductsLoaded) return;

  // 下单、调拨弹窗同时打开时只发起一次全量加载。
  if (!allProductsPromise) {
    allProductsPromise = fetchAllProducts()
      .then((products) => {
        state.allProducts = products;
        state.allProductsLoaded = true;
        renderTransferProductOptions();
      })
      .finally(() => {
        allProductsPromise = null;
      });
  }

  return allProductsPromise;
}

function renderTransferProductOptions() {
  const options = state.allProducts.length
    ? state.allProducts.map((product) => (
      `<option value="${product.id}">${escapeHtml(product.product_name)} / ${escapeHtml(product.sku)} / 库存 ${product.quantity}</option>`
    )).join("")
    : '<option value="">没有可用商品</option>';

  $("transferProductSelect").innerHTML = options;
}

/* ------------------------------------------------------------------ *
 * 4. 订单
 * ------------------------------------------------------------------ */
async function loadOrders() {
  const params = new URLSearchParams({
    page: String(state.orders.page),
    size: String(state.orders.size),
  });
  if (state.orders.status) params.set("status", state.orders.status);

  const data = await api(`/api/orders?${params.toString()}`);
  state.orders.items = data.items;
  state.orders.total = data.total;
  renderOrders();
  renderOrderPager();
}

function orderProfitHtml(order) {
  if (order.status === "CANCELLED") {
    return '<span class="muted-text">-</span>';
  }

  const profit = Number(order.profit_amount ?? 0);
  const tone = profit < 0 ? "money-neg" : "money-pos";
  const hint = order.status === "CREATED"
    ? '<span class="product-meta">预计</span>'
    : "";
  return `<span class="${tone}">${formatMoney(profit)}</span>${hint}`;
}

function renderOrders() {
  const tbody = $("orderTableBody");
  const empty = $("orderEmpty");
  empty.hidden = state.orders.items.length > 0;

  if (!state.orders.items.length) {
    tbody.innerHTML = "";
    return;
  }

  const writable = canWrite();

  tbody.innerHTML = state.orders.items.map((order) => {
    const itemsText = order.items.map((item) => {
      const returned = item.returned_quantity
        ? `（已退 ${item.returned_quantity}）`
        : "";
      return `${escapeHtml(item.product_name)} × ${item.quantity}${returned}`;
    }).join("；");

    const canPay = writable && order.status === "CREATED";
    const canCancel = writable && order.status === "CREATED";
    const canReturn = writable
      && (order.status === "PAID" || order.status === "PARTIALLY_RETURNED");

    return `
      <tr>
        <td>
          <span class="product-name">${escapeHtml(order.order_no)}</span>
          <span class="product-meta">ID: ${order.id}${order.paid_at ? ` · 支付：${escapeHtml(order.payment_method || "-")}` : ""}</span>
        </td>
        <td>${orderBadge(order.status)}</td>
        <td class="num">
          ${formatMoney(order.total_amount)}
          ${Number(order.refunded_amount) > 0 ? `<span class="product-meta">已退 ${formatMoney(order.refunded_amount)}</span>` : ""}
        </td>
        <td class="num">${orderProfitHtml(order)}</td>
        <td class="order-goods">${itemsText}</td>
        <td>${escapeHtml(order.operator || "-")}</td>
        <td>${formatDate(order.created_at)}</td>
        <td>
          <div class="row-actions">
            ${canPay ? `<button class="mini-btn" type="button" data-order-action="pay" data-id="${order.id}">支付</button>` : ""}
            ${canCancel ? `<button class="mini-btn danger" type="button" data-order-action="cancel" data-id="${order.id}">取消</button>` : ""}
            ${canReturn ? `<button class="mini-btn warn" type="button" data-order-action="return" data-id="${order.id}">退货</button>` : ""}
            ${!writable ? '<span class="muted-text">只读</span>' : ""}
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

function renderOrderPager() {
  renderPagerCore("order", "orders", "单");
}

async function payOrder(orderId) {
  const order = await api(`/api/orders/${orderId}/pay`, {
    method: "POST",
    body: JSON.stringify({ payment_method: "BALANCE" }),
  });
  toast(`支付成功，本单利润 ${formatMoney(order.profit_amount)}`);
  await Promise.all([loadOrders(), loadOrderStats()]);
}

async function cancelOrder(orderId) {
  const reason = window.prompt("请输入取消原因（可留空）", "客户取消");
  if (reason === null) return;

  await api(`/api/orders/${orderId}/cancel`, {
    method: "POST",
    body: JSON.stringify({ reason: trimOrNull(reason) }),
  });
  toast("订单已取消，库存已回补");
  await Promise.all([loadOrders(), refreshStatsAndProducts()]);
}

async function openReturnModal(orderId) {
  const order = await api(`/api/orders/${orderId}`);
  state.returnOrder = order;

  $("returnOrderId").value = order.id;
  $("returnOrderInfo").textContent =
    `${order.order_no} · 订单金额 ${formatMoney(order.total_amount)} · 已退 ${formatMoney(order.refunded_amount)}`;
  $("returnReason").value = "";

  const rows = order.items.filter(
    (item) => item.quantity - item.returned_quantity > 0,
  );

  $("returnItems").innerHTML = rows.length
    ? rows.map((item) => {
      const remaining = item.quantity - item.returned_quantity;
      return `
        <div class="return-row">
          <div>
            <strong>${escapeHtml(item.product_name)}</strong>
            <small>${escapeHtml(item.sku)} · ${formatMoney(item.unit_price)} · 可退 ${remaining} 件</small>
          </div>
          <input
            type="number"
            min="0"
            max="${remaining}"
            value="0"
            data-return-item="${item.id}"
            aria-label="退货数量"
          >
        </div>
      `;
    }).join("")
    : '<div class="order-empty">该订单没有可退商品</div>';

  $("returnModal").hidden = false;
}

async function submitReturn(event) {
  event.preventDefault();

  const orderId = Number($("returnOrderId").value);
  const items = [];

  document.querySelectorAll("input[data-return-item]").forEach((input) => {
    const quantity = Number(input.value) || 0;
    if (quantity > 0) {
      items.push({
        order_item_id: Number(input.dataset.returnItem),
        quantity,
      });
    }
  });

  if (!items.length) {
    toast("请填写至少一个退货数量", "error");
    return;
  }

  try {
    const result = await api(`/api/orders/${orderId}/returns`, {
      method: "POST",
      body: JSON.stringify({
        items,
        reason: trimOrNull($("returnReason").value),
      }),
    });
    toast(`退货成功，退款 ${formatMoney(result.refund_amount)}，库存已回补`);
    closeModal("returnModal");
    await Promise.all([loadOrders(), refreshStatsAndProducts()]);
    state.allProductsLoaded = false;
  } catch (error) {
    showError(error);
  }
}

async function openOrderModal() {
  state.orderItems = [];
  $("orderOperator").value = "";
  $("orderRemark").value = "";
  $("orderQuantity").value = 1;
  resetOrderProductPicker();
  renderOrderItems();
  $("orderModal").hidden = false;

  try {
    await ensureAllProducts();
    renderOrderProductList({ show: false });
  } catch (error) {
    showError(error);
  }
}

/* 商品搜索下拉框：输入关键字过滤，点击或回车选中 */
function resetOrderProductPicker() {
  state.orderProductId = null;
  state.orderProductMatches = [];
  state.orderProductActive = -1;
  $("orderProductSearch").value = "";
  $("orderProductList").innerHTML = "";
  $("orderProductList").hidden = true;
}

function searchOrderProducts(keyword) {
  const text = String(keyword || "").trim().toLowerCase();
  const products = state.allProducts;

  if (!text) return products.slice(0, 30);
  return products.filter((product) => (
    product.product_name.toLowerCase().includes(text)
    || product.sku.toLowerCase().includes(text)
  )).slice(0, 30);
}

function renderOrderProductList({ show = true } = {}) {
  const list = $("orderProductList");
  const text = $("orderProductSearch").value;

  if (!state.allProducts.length) {
    state.orderProductMatches = [];
    list.innerHTML = '<div class="combo-empty">商品加载中，请稍候…</div>';
    list.hidden = !show;
    return;
  }

  state.orderProductMatches = searchOrderProducts(text);

  if (!state.orderProductMatches.length) {
    list.innerHTML = '<div class="combo-empty">没有匹配的商品</div>';
    list.hidden = !show;
    return;
  }

  if (state.orderProductActive >= state.orderProductMatches.length) {
    state.orderProductActive = -1;
  }

  list.innerHTML = state.orderProductMatches.map((product, index) => `
    <div
      class="combo-item${index === state.orderProductActive ? " active" : ""}"
      data-product-id="${product.id}"
    >
      <span class="combo-name">${escapeHtml(product.product_name)}</span>
      <span class="combo-meta">${escapeHtml(product.sku)} · 库存 ${product.quantity}</span>
    </div>
  `).join("");
  list.hidden = !show;
}

function selectOrderProduct(product) {
  state.orderProductId = product.id;
  state.orderProductActive = -1;
  $("orderProductSearch").value = `${product.product_name} / ${product.sku}`;
  $("orderProductList").hidden = true;
  $("orderQuantity").focus();
  $("orderQuantity").select();
}

function moveOrderProductActive(step) {
  const count = state.orderProductMatches.length;
  if (!count) return;
  const next = state.orderProductActive + step;
  state.orderProductActive = (next + count) % count;
  renderOrderProductList();
}

function addOrderItem() {
  const productId = state.orderProductId;
  const quantity = Number($("orderQuantity").value);

  if (!productId) {
    toast("请先搜索并选择商品", "error");
    return;
  }
  if (!Number.isInteger(quantity) || quantity < 1) {
    toast("请填写正确的数量", "error");
    return;
  }

  const product = state.allProducts.find((item) => item.id === productId);
  if (!product) {
    toast("商品不存在，请刷新后重试", "error");
    return;
  }

  const existing = state.orderItems.find((item) => item.product.id === productId);
  if (existing) {
    existing.quantity += quantity;
  } else {
    state.orderItems.push({ product, quantity });
  }

  resetOrderProductPicker();
  $("orderQuantity").value = 1;
  renderOrderItems();
  $("orderProductSearch").focus();
}

function updateOrderTotal() {
  let total = 0;
  let profit = 0;

  state.orderItems.forEach((item) => {
    const price = Number(item.product.price);
    const cost = Number(item.product.cost ?? 0);
    total += price * item.quantity;
    profit += (price - cost) * item.quantity;
  });

  $("orderTotal").textContent = formatMoney(total);
  $("orderProfit").textContent = formatMoney(profit);
  $("orderProfit").parentElement.classList.toggle("money-neg", profit < 0);
}

function renderOrderItems() {
  const container = $("orderItems");

  if (!state.orderItems.length) {
    container.innerHTML = '<div class="order-empty">还没有添加商品</div>';
    updateOrderTotal();
    return;
  }

  container.innerHTML = state.orderItems.map((item, index) => {
    const subtotal = Number(item.product.price) * item.quantity;
    return `
      <div class="order-row">
        <div>
          <strong>${escapeHtml(item.product.product_name)}</strong>
          <small>${escapeHtml(item.product.sku)} · ${formatMoney(item.product.price)}</small>
        </div>
        <input
          type="number"
          min="1"
          value="${item.quantity}"
          data-order-index="${index}"
          aria-label="数量"
        >
        <div class="order-subtotal">${formatMoney(subtotal)}</div>
        <button
          class="remove-item"
          type="button"
          data-remove-index="${index}"
          aria-label="移除"
        >×</button>
      </div>
    `;
  }).join("");

  updateOrderTotal();
}

async function submitOrder(event) {
  event.preventDefault();

  if (!state.orderItems.length) {
    toast("请先添加订单商品", "error");
    return;
  }

  const payload = {
    items: state.orderItems.map((item) => ({
      product_id: item.product.id,
      quantity: item.quantity,
    })),
    operator: trimOrNull($("orderOperator").value),
    remark: trimOrNull($("orderRemark").value),
  };

  try {
    const order = await api("/api/orders", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    toast(
      `订单 ${order.order_no} 创建成功，已扣减库存，预计利润 ${formatMoney(order.profit_amount)}`,
    );
    closeModal("orderModal");
    state.allProductsLoaded = false;
    await Promise.all([refreshStatsAndProducts(), loadOrders()]);
  } catch (error) {
    showError(error);
  }
}

/* ------------------------------------------------------------------ *
 * 5. 任务
 * ------------------------------------------------------------------ */
async function loadTasks() {
  const params = new URLSearchParams({
    page: String(state.tasks.page),
    size: String(state.tasks.size),
  });
  if (state.tasks.status) params.set("status", state.tasks.status);

  const [data, stats] = await Promise.all([
    api(`/api/tasks?${params.toString()}`),
    api("/api/tasks/stats"),
  ]);

  state.tasks.items = data.items;
  state.tasks.total = data.total;
  renderTasks();
  renderTaskStats(stats);
  renderTaskPager();
}

function renderTaskStats(stats) {
  const order = ["PENDING", "IN_PROGRESS", "DONE", "CANCELLED"];
  $("taskStats").innerHTML = order.map((status) => `
    <span class="stat-chip">
      ${escapeHtml(TASK_STATUS[status])}
      <strong>${stats[status] || 0}</strong>
    </span>
  `).join("");
}

function renderTasks() {
  const tbody = $("taskTableBody");
  const empty = $("taskEmpty");
  empty.hidden = state.tasks.items.length > 0;

  if (!state.tasks.items.length) {
    tbody.innerHTML = "";
    return;
  }

  const writable = canWrite();

  tbody.innerHTML = state.tasks.items.map((task) => {
    const actions = [];
    if (writable) {
      actions.push(`<button class="mini-btn" type="button" data-task-action="edit" data-id="${task.id}">编辑</button>`);
      if (task.status === "PENDING") {
        actions.push(`<button class="mini-btn" type="button" data-task-action="start" data-id="${task.id}">开始</button>`);
      }
      if (task.status === "IN_PROGRESS" || task.status === "PENDING") {
        actions.push(`<button class="mini-btn" type="button" data-task-action="done" data-id="${task.id}">完成</button>`);
      }
      if (task.status !== "DONE" && task.status !== "CANCELLED") {
        actions.push(`<button class="mini-btn danger" type="button" data-task-action="cancel" data-id="${task.id}">取消</button>`);
      }
      if (task.status === "CANCELLED") {
        actions.push(`<button class="mini-btn danger" type="button" data-task-action="delete" data-id="${task.id}">删除</button>`);
      }
    }

    return `
      <tr>
        <td class="product-cell">
          <span class="product-name">${escapeHtml(task.title)}</span>
          <span class="product-meta">${escapeHtml(task.description || "无描述")}</span>
        </td>
        <td>${taskBadge(task.status)}</td>
        <td>${badge(task.priority === "URGENT" ? "badge-low" : task.priority === "HIGH" ? "badge-warn" : "badge-muted", PRIORITY_LABELS[task.priority] || task.priority)}</td>
        <td>${escapeHtml(task.assignee || "-")}</td>
        <td>${formatDate(task.due_at)}</td>
        <td>${escapeHtml(task.created_by || "-")}</td>
        <td>
          <div class="row-actions">
            ${actions.join("") || '<span class="muted-text">只读</span>'}
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

function renderTaskPager() {
  renderPagerCore("task", "tasks", "条");
}

function openTaskModal(task = null) {
  $("taskId").value = task?.id || "";
  $("taskModalTitle").textContent = task ? "编辑任务" : "新建任务";
  $("taskTitle").value = task?.title || "";
  $("taskDescription").value = task?.description || "";
  $("taskPriority").value = task?.priority || "NORMAL";
  $("taskAssignee").value = task?.assignee || "";
  $("taskDueAt").value = task?.due_at ? String(task.due_at).slice(0, 16) : "";
  $("taskModal").hidden = false;
  $("taskTitle").focus();
}

async function submitTask(event) {
  event.preventDefault();

  const taskId = $("taskId").value;
  const payload = {
    title: $("taskTitle").value.trim(),
    description: trimOrNull($("taskDescription").value),
    priority: $("taskPriority").value,
    assignee: trimOrNull($("taskAssignee").value),
    due_at: $("taskDueAt").value
      ? new Date($("taskDueAt").value).toISOString()
      : null,
  };

  try {
    if (taskId) {
      // 编辑时允许清空截止时间，因此显式传 due_at。
      await api(`/api/tasks/${taskId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      toast("任务已更新");
    } else {
      await api("/api/tasks", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      toast("任务已创建");
    }
    closeModal("taskModal");
    await loadTasks();
  } catch (error) {
    showError(error);
  }
}

async function updateTaskStatus(taskId, changes, message) {
  await api(`/api/tasks/${taskId}`, {
    method: "PATCH",
    body: JSON.stringify(changes),
  });
  toast(message);
  await loadTasks();
}

async function deleteTask(taskId) {
  if (!window.confirm("确定删除这个已取消的任务吗？")) return;
  await api(`/api/tasks/${taskId}`, { method: "DELETE" });
  toast("任务已删除");
  await loadTasks();
}

/* ------------------------------------------------------------------ *
 * 6. 盘点
 * ------------------------------------------------------------------ */
async function loadStocktakes() {
  const params = new URLSearchParams({
    page: String(state.stocktakes.page),
    size: String(state.stocktakes.size),
  });

  const data = await api(`/api/stocktakes?${params.toString()}`);
  state.stocktakes.items = data.items;
  state.stocktakes.total = data.total;
  renderStocktakes();
  renderStocktakePager();
}

function renderStocktakes() {
  const tbody = $("stocktakeTableBody");
  const empty = $("stocktakeEmpty");
  empty.hidden = state.stocktakes.items.length > 0;

  if (!state.stocktakes.items.length) {
    tbody.innerHTML = "";
    return;
  }

  const writable = canWrite();

  tbody.innerHTML = state.stocktakes.items.map((item) => `
    <tr>
      <td>
        <span class="product-name">${escapeHtml(item.stocktake_no)}</span>
        <span class="product-meta">ID: ${item.id}${item.remark ? ` · ${escapeHtml(item.remark)}` : ""}</span>
      </td>
      <td>${stocktakeBadge(item.status)}</td>
      <td>${escapeHtml(item.scope || "全部分类")}</td>
      <td class="num">${item.items.length}</td>
      <td>${escapeHtml(item.operator || "-")}</td>
      <td>${formatDate(item.created_at)}</td>
      <td>
        <div class="row-actions">
          ${writable && item.status === "COUNTING"
            ? `<button class="mini-btn" type="button" data-stocktake-action="count" data-id="${item.id}">录入实数</button>
               <button class="mini-btn danger" type="button" data-stocktake-action="cancel" data-id="${item.id}">取消</button>`
            : ""}
          <button class="mini-btn" type="button" data-stocktake-action="view" data-id="${item.id}">查看</button>
        </div>
      </td>
    </tr>
  `).join("");
}

function renderStocktakePager() {
  renderPagerCore("stocktake", "stocktakes", "单");
}

async function openCountModal(stocktakeId) {
  const stocktake = await api(`/api/stocktakes/${stocktakeId}`);
  state.countStocktake = stocktake;

  $("countStocktakeId").value = stocktake.id;
  $("countModalTitle").textContent = stocktake.status === "COUNTING"
    ? "录入实盘数量"
    : "盘点明细";
  $("countModalInfo").textContent =
    `${stocktake.stocktake_no} · ${stocktake.scope || "全部分类"} · ${STOCKTAKE_STATUS[stocktake.status] || stocktake.status}`;

  const readonly = stocktake.status !== "COUNTING" || !canWrite();

  $("countItems").innerHTML = stocktake.items.map((item) => `
    <div class="count-row">
      <div>
        <strong>${escapeHtml(item.product_name)}</strong>
        <small>${escapeHtml(item.sku)} · 账面 ${item.expected_quantity}${item.difference == null ? "" : ` · 差异 ${item.difference}`}</small>
      </div>
      <input
        type="number"
        min="0"
        value="${item.counted_quantity ?? item.expected_quantity}"
        data-count-product="${item.product_id}"
        aria-label="实盘数量"
        ${readonly ? "disabled" : ""}
      >
    </div>
  `).join("");

  $("saveCountBtn").hidden = readonly;
  $("confirmStocktakeBtn").hidden = readonly;
  $("countModal").hidden = false;
}

function collectCounts() {
  const items = [];
  document.querySelectorAll("input[data-count-product]").forEach((input) => {
    const value = input.value;
    if (value === "") return;
    items.push({
      product_id: Number(input.dataset.countProduct),
      counted_quantity: Number(value),
    });
  });
  return items;
}

async function saveCounts(showMessage = true) {
  const stocktakeId = Number($("countStocktakeId").value);
  const items = collectCounts();
  if (!items.length) {
    toast("请至少录入一个实盘数量", "error");
    return false;
  }

  await api(`/api/stocktakes/${stocktakeId}/count`, {
    method: "POST",
    body: JSON.stringify({ items }),
  });
  if (showMessage) toast("实盘数量已保存");
  return true;
}

async function confirmStocktake() {
  const stocktakeId = Number($("countStocktakeId").value);
  if (!window.confirm("确认盘点后将按实盘数量修正库存，是否继续？")) return;

  try {
    if (!(await saveCounts(false))) return;
    const result = await api(`/api/stocktakes/${stocktakeId}/confirm`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    toast(`盘点 ${result.stocktake_no} 已确认，库存已调整`);
    closeModal("countModal");
    await Promise.all([loadStocktakes(), refreshStatsAndProducts()]);
    state.allProductsLoaded = false;
  } catch (error) {
    showError(error);
  }
}

/* ------------------------------------------------------------------ *
 * 7. 调拨与仓库
 * ------------------------------------------------------------------ */
async function loadWarehouses() {
  state.warehouses = await api("/api/warehouses");

  const options = state.warehouses.map(
    (warehouse) => `<option value="${warehouse.id}">${escapeHtml(warehouse.name)}（${escapeHtml(warehouse.code)}）</option>`,
  ).join("");

  $("transferFrom").innerHTML = options;
  $("transferTo").innerHTML = options;
  if (state.warehouses.length > 1) {
    $("transferTo").value = String(state.warehouses[1].id);
  }

  $("warehouseBar").innerHTML = state.warehouses.map((warehouse) => `
    <span class="stat-chip">
      ${escapeHtml(warehouse.name)}
      <strong>${escapeHtml(warehouse.code)}</strong>
      ${warehouse.is_default ? '<span class="pill tiny">默认</span>' : ""}
    </span>
  `).join("");
}

async function loadTransfers() {
  const params = new URLSearchParams({
    page: String(state.transfers.page),
    size: String(state.transfers.size),
  });

  const data = await api(`/api/transfers?${params.toString()}`);
  state.transfers.items = data.items;
  state.transfers.total = data.total;
  renderTransfers();
  renderTransferPager();
}

function renderTransfers() {
  const tbody = $("transferTableBody");
  const empty = $("transferEmpty");
  empty.hidden = state.transfers.items.length > 0;

  if (!state.transfers.items.length) {
    tbody.innerHTML = "";
    return;
  }

  tbody.innerHTML = state.transfers.items.map((transfer) => {
    const goods = transfer.items
      .map((item) => `${escapeHtml(item.product_name)} × ${item.quantity}`)
      .join("；");

    return `
      <tr>
        <td>
          <span class="product-name">${escapeHtml(transfer.transfer_no)}</span>
          <span class="product-meta">${goods}</span>
        </td>
        <td>${escapeHtml(transfer.from_warehouse.name)} → ${escapeHtml(transfer.to_warehouse.name)}</td>
        <td class="num">${transfer.items.length}</td>
        <td>${escapeHtml(transfer.operator || "-")}</td>
        <td>${formatDate(transfer.created_at)}</td>
        <td>${badge("badge-ok", "已完成")}</td>
      </tr>
    `;
  }).join("");
}

function renderTransferPager() {
  renderPagerCore("transfer", "transfers", "单");
}

function openTransferModal() {
  if (state.warehouses.length < 2) {
    toast("至少需要两个仓库才能调拨，请先新建仓库", "error");
    return;
  }

  state.transferItems = [];
  $("transferOperator").value = "";
  $("transferRemark").value = "";
  $("transferQuantity").value = 1;
  renderTransferItems();
  $("transferModal").hidden = false;

  ensureAllProducts().catch(showError);
}

function addTransferItem() {
  const productId = Number($("transferProductSelect").value);
  const quantity = Number($("transferQuantity").value);

  if (!productId || !Number.isInteger(quantity) || quantity < 1) {
    toast("请选择商品并填写正确的数量", "error");
    return;
  }

  const product = state.allProducts.find((item) => item.id === productId);
  if (!product) {
    toast("商品不存在，请刷新后重试", "error");
    return;
  }

  const existing = state.transferItems.find(
    (item) => item.product.id === productId,
  );
  if (existing) {
    existing.quantity += quantity;
  } else {
    state.transferItems.push({ product, quantity });
  }

  $("transferQuantity").value = 1;
  renderTransferItems();
}

function renderTransferItems() {
  const container = $("transferItems");
  if (!state.transferItems.length) {
    container.innerHTML = '<div class="order-empty">还没有添加商品</div>';
    return;
  }

  container.innerHTML = state.transferItems.map((item, index) => `
    <div class="order-row">
      <div>
        <strong>${escapeHtml(item.product.product_name)}</strong>
        <small>${escapeHtml(item.product.sku)} · 总库存 ${item.product.quantity}</small>
      </div>
      <input type="number" min="1" value="${item.quantity}" data-transfer-index="${index}" aria-label="数量">
      <div class="order-subtotal">×</div>
      <button class="remove-item" type="button" data-transfer-remove="${index}" aria-label="移除">×</button>
    </div>
  `).join("");
}

async function submitTransfer(event) {
  event.preventDefault();

  if (!state.transferItems.length) {
    toast("请先添加调拨商品", "error");
    return;
  }

  const payload = {
    from_warehouse_id: Number($("transferFrom").value),
    to_warehouse_id: Number($("transferTo").value),
    items: state.transferItems.map((item) => ({
      product_id: item.product.id,
      quantity: item.quantity,
    })),
    operator: trimOrNull($("transferOperator").value),
    remark: trimOrNull($("transferRemark").value),
  };

  try {
    const transfer = await api("/api/transfers", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    toast(`调拨单 ${transfer.transfer_no} 已完成`);
    closeModal("transferModal");
    await Promise.all([loadTransfers(), loadWarehouses()]);
  } catch (error) {
    showError(error);
  }
}

async function submitWarehouse(event) {
  event.preventDefault();

  try {
    const warehouse = await api("/api/warehouses", {
      method: "POST",
      body: JSON.stringify({
        code: $("warehouseCode").value.trim(),
        name: $("warehouseName").value.trim(),
        address: trimOrNull($("warehouseAddress").value),
      }),
    });
    toast(`仓库 ${warehouse.name} 已创建`);
    closeModal("warehouseModal");
    $("warehouseForm").reset();
    await loadWarehouses();
  } catch (error) {
    showError(error);
  }
}

/* ------------------------------------------------------------------ *
 * 8. 用户管理
 * ------------------------------------------------------------------ */
async function loadUsers() {
  const data = await api("/api/users?page=1&size=100");
  const tbody = $("userTableBody");

  tbody.innerHTML = data.items.map((user) => `
    <tr>
      <td><span class="product-name">${escapeHtml(user.username)}</span></td>
      <td>${escapeHtml(user.full_name || "-")}</td>
      <td>
        <select data-user-role="${user.id}" ${user.role === "admin" ? "" : ""}>
          <option value="admin" ${user.role === "admin" ? "selected" : ""}>管理员</option>
          <option value="operator" ${user.role === "operator" ? "selected" : ""}>操作员</option>
          <option value="viewer" ${user.role === "viewer" ? "selected" : ""}>只读用户</option>
        </select>
      </td>
      <td>${user.is_active ? badge("badge-ok", "启用") : badge("badge-muted", "禁用")}</td>
      <td>${formatDate(user.last_login_at)}</td>
      <td>
        <div class="row-actions">
          <button class="mini-btn ${user.is_active ? "danger" : ""}" type="button" data-user-toggle="${user.id}" data-active="${user.is_active ? "1" : "0"}">
            ${user.is_active ? "禁用" : "启用"}
          </button>
        </div>
      </td>
    </tr>
  `).join("");
}

async function submitUser(event) {
  event.preventDefault();

  try {
    await api("/api/users", {
      method: "POST",
      body: JSON.stringify({
        username: $("userUsername").value.trim(),
        password: $("userPassword").value,
        full_name: trimOrNull($("userFullName").value),
        role: $("userRole").value,
      }),
    });
    toast("用户创建成功");
    closeModal("userModal");
    $("userForm").reset();
    await loadUsers();
  } catch (error) {
    showError(error);
  }
}

/* ------------------------------------------------------------------ *
 * 9. 标签页、刷新与事件绑定
 * ------------------------------------------------------------------ */
async function loadCurrentTab() {
  switch (state.tab) {
    case "products":
      await refreshStatsAndProducts();
      break;
    case "orders":
      await loadOrders();
      break;
    case "tasks":
      await loadTasks();
      break;
    case "stocktakes":
      await loadStocktakes();
      break;
    case "transfers":
      await Promise.all([loadWarehouses(), loadTransfers()]);
      break;
    case "users":
      if (isAdmin()) await loadUsers();
      break;
    default:
      break;
  }
}

async function switchTab(tab) {
  state.tab = tab;

  document.querySelectorAll("#tabs .tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tab);
  });

  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.hidden = panel.id !== `panel-${tab}`;
  });

  try {
    await loadCurrentTab();
  } catch (error) {
    showError(error);
  }
}

async function startApp() {
  if (!state.user) return;

  // 用户角色可能已被管理员修改，避免停留在无权访问的标签页。
  if (!isAdmin() && state.tab === "users") {
    state.tab = "products";
  }

  applyAuthUi();
  $("loginLayer").hidden = true;

  try {
    await loadCategories();
  } catch (error) {
    showError(error);
  }

  await switchTab(state.tab);
}

function bindEvents() {
  // 登录
  $("loginForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    $("loginSubmitBtn").disabled = true;
    try {
      await login($("loginUsername").value.trim(), $("loginPassword").value);
    } catch (error) {
      showError(error);
    } finally {
      $("loginSubmitBtn").disabled = false;
    }
  });

  $("logoutBtn").addEventListener("click", () => {
    state.token = "";
    state.user = null;
    persistAuth();
    $("loginLayer").hidden = false;
    toast("已退出登录");
  });

  // 标签页
  $("tabs").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-tab]");
    if (!button) return;
    switchTab(button.dataset.tab);
  });

  // 商品筛选
  $("searchBtn").addEventListener("click", () => {
    state.products.page = 1;
    state.products.keyword = $("keywordInput").value.trim();
    state.products.categoryId = $("categorySelect").value;
    state.products.lowStockOnly = $("lowStockOnly").checked;
    loadProducts().catch(showError);
  });

  $("keywordInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter") $("searchBtn").click();
  });

  $("categorySelect").addEventListener("change", () => {
    state.products.page = 1;
    state.products.categoryId = $("categorySelect").value;
    loadProducts().catch(showError);
  });

  $("lowStockOnly").addEventListener("change", () => {
    state.products.page = 1;
    state.products.lowStockOnly = $("lowStockOnly").checked;
    loadProducts().catch(showError);
  });

  $("refreshBtn").addEventListener("click", () => {
    if (state.tab === "products") {
      refreshStatsAndProducts().catch(showError);
    } else {
      loadCurrentTab().catch(showError);
    }
  });

  $("openOrderBtn").addEventListener("click", () => openOrderModal());

  $("productTableBody").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;

    const product = state.products.items.find(
      (item) => item.id === Number(button.dataset.id),
    );
    if (product) openStockModal(product, button.dataset.action);
  });

  bindPager("", "products", loadProducts);

  $("stockForm").addEventListener("submit", submitStock);
  $("orderForm").addEventListener("submit", submitOrder);
  $("addOrderItemBtn").addEventListener("click", addOrderItem);

  // 订单弹窗里的商品搜索框
  $("orderProductSearch").addEventListener("input", () => {
    state.orderProductId = null;
    state.orderProductActive = -1;
    renderOrderProductList();
  });

  $("orderProductSearch").addEventListener("focus", () => {
    // 已选中商品时保持当前选择，重新输入会自动切换为搜索状态。
    if (state.orderProductId) return;
    renderOrderProductList();
  });

  $("orderProductSearch").addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      moveOrderProductActive(1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      moveOrderProductActive(-1);
    } else if (event.key === "Enter") {
      // 回车用于选中商品，避免误提交整个订单表单。
      event.preventDefault();
      if ($("orderProductList").hidden) renderOrderProductList();

      if (state.orderProductActive >= 0) {
        const product = state.orderProductMatches[state.orderProductActive];
        if (product) selectOrderProduct(product);
      } else if (!state.orderProductId) {
        const product = state.orderProductMatches[0];
        if (product) selectOrderProduct(product);
      } else {
        $("orderProductList").hidden = true;
      }
    } else if (event.key === "Escape") {
      // 列表展开时先收起列表，不再关闭整个弹窗。
      event.stopPropagation();
      $("orderProductList").hidden = true;
    }
  });

  $("orderProductList").addEventListener("mousedown", (event) => {
    const item = event.target.closest(".combo-item");
    if (!item) return;
    event.preventDefault();
    const product = state.allProducts.find(
      (entry) => entry.id === Number(item.dataset.productId),
    );
    if (product) selectOrderProduct(product);
  });

  document.addEventListener("click", (event) => {
    if (!$("orderProductCombo").contains(event.target)) {
      $("orderProductList").hidden = true;
    }
  });
  $("returnForm").addEventListener("submit", submitReturn);
  $("taskForm").addEventListener("submit", submitTask);
  $("stocktakeForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const stocktake = await api("/api/stocktakes", {
        method: "POST",
        body: JSON.stringify({
          category_id: $("stocktakeCategory").value
            ? Number($("stocktakeCategory").value)
            : null,
          remark: trimOrNull($("stocktakeRemark").value),
        }),
      });
      toast(`盘点单 ${stocktake.stocktake_no} 已创建，共 ${stocktake.items.length} 个商品`);
      closeModal("stocktakeModal");
      $("stocktakeRemark").value = "";
      await loadStocktakes();
      await openCountModal(stocktake.id);
    } catch (error) {
      showError(error);
    }
  });

  $("countForm").addEventListener("submit", (event) => {
    event.preventDefault();
    saveCounts().catch(showError);
  });
  $("confirmStocktakeBtn").addEventListener("click", () => {
    confirmStocktake().catch(showError);
  });

  $("transferForm").addEventListener("submit", submitTransfer);
  $("addTransferItemBtn").addEventListener("click", addTransferItem);
  $("warehouseForm").addEventListener("submit", submitWarehouse);
  $("userForm").addEventListener("submit", submitUser);

  // 订单操作
  $("orderTableBody").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-order-action]");
    if (!button) return;

    const orderId = Number(button.dataset.id);
    try {
      if (button.dataset.orderAction === "pay") {
        await payOrder(orderId);
      } else if (button.dataset.orderAction === "cancel") {
        await cancelOrder(orderId);
      } else if (button.dataset.orderAction === "return") {
        await openReturnModal(orderId);
      }
    } catch (error) {
      showError(error);
    }
  });

  $("orderStatusFilter").addEventListener("change", () => {
    state.orders.page = 1;
    state.orders.status = $("orderStatusFilter").value;
    loadOrders().catch(showError);
  });
  $("refreshOrdersBtn").addEventListener("click", () => loadOrders().catch(showError));

  bindPager("order", "orders", loadOrders);

  // 任务
  $("openTaskBtn").addEventListener("click", () => openTaskModal());
  $("taskStatusFilter").addEventListener("change", () => {
    state.tasks.page = 1;
    state.tasks.status = $("taskStatusFilter").value;
    loadTasks().catch(showError);
  });
  bindPager("task", "tasks", loadTasks);

  $("taskTableBody").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-task-action]");
    if (!button) return;

    const taskId = Number(button.dataset.id);
    const action = button.dataset.taskAction;

    try {
      if (action === "edit") {
        const task = state.tasks.items.find((item) => item.id === taskId);
        if (task) openTaskModal(task);
      } else if (action === "start") {
        await updateTaskStatus(taskId, { status: "IN_PROGRESS" }, "任务已开始");
      } else if (action === "done") {
        await updateTaskStatus(taskId, { status: "DONE" }, "任务已完成");
      } else if (action === "cancel") {
        await updateTaskStatus(taskId, { status: "CANCELLED" }, "任务已取消");
      } else if (action === "delete") {
        await deleteTask(taskId);
      }
    } catch (error) {
      showError(error);
    }
  });

  // 盘点
  $("refreshStocktakesBtn").addEventListener("click", () => loadStocktakes().catch(showError));
  $("openStocktakeBtn").addEventListener("click", () => {
    $("stocktakeModal").hidden = false;
  });
  bindPager("stocktake", "stocktakes", loadStocktakes);

  $("stocktakeTableBody").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-stocktake-action]");
    if (!button) return;

    const stocktakeId = Number(button.dataset.id);
    const action = button.dataset.stocktakeAction;

    try {
      if (action === "count" || action === "view") {
        await openCountModal(stocktakeId);
      } else if (action === "cancel") {
        if (!window.confirm("确定取消这张盘点单吗？不会影响库存。")) return;
        await api(`/api/stocktakes/${stocktakeId}/cancel`, {
          method: "POST",
          body: JSON.stringify({}),
        });
        toast("盘点单已取消");
        await loadStocktakes();
      }
    } catch (error) {
      showError(error);
    }
  });

  // 调拨
  $("refreshTransfersBtn").addEventListener("click", () => {
    Promise.all([loadWarehouses(), loadTransfers()]).catch(showError);
  });
  $("openWarehouseBtn").addEventListener("click", () => {
    $("warehouseModal").hidden = false;
  });
  $("openTransferBtn").addEventListener("click", openTransferModal);
  bindPager("transfer", "transfers", loadTransfers);

  // 用户
  $("refreshUsersBtn").addEventListener("click", () => loadUsers().catch(showError));
  $("openUserBtn").addEventListener("click", () => {
    $("userModal").hidden = false;
  });

  $("userTableBody").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-user-toggle]");
    if (!button) return;

    const userId = Number(button.dataset.userToggle);
    const nextActive = button.dataset.active !== "1";
    try {
      await api(`/api/users/${userId}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: nextActive }),
      });
      toast(nextActive ? "用户已启用" : "用户已禁用");
      await loadUsers();
    } catch (error) {
      showError(error);
    }
  });

  $("userTableBody").addEventListener("change", async (event) => {
    const select = event.target.closest("select[data-user-role]");
    if (!select) return;

    try {
      await api(`/api/users/${select.dataset.userRole}`, {
        method: "PATCH",
        body: JSON.stringify({ role: select.value }),
      });
      toast("角色已更新");
      await loadUsers();
    } catch (error) {
      showError(error);
    }
  });

  // 弹窗关闭
  document.querySelectorAll("[data-close]").forEach((button) => {
    button.addEventListener("click", () => closeModal(button.dataset.close));
  });

  document.querySelectorAll(".modal-layer, .login-layer").forEach((layer) => {
    layer.addEventListener("click", (event) => {
      if (event.target === layer && layer.id !== "loginLayer") {
        closeModal(layer.id);
      }
    });
  });

  // 订单弹窗内的商品增删
  $("orderItems").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-remove-index]");
    if (!button) return;
    state.orderItems.splice(Number(button.dataset.removeIndex), 1);
    renderOrderItems();
  });

  $("orderItems").addEventListener("input", (event) => {
    const input = event.target.closest("input[data-order-index]");
    if (!input) return;

    const index = Number(input.dataset.orderIndex);
    const quantity = Math.max(1, Number(input.value) || 1);
    state.orderItems[index].quantity = quantity;

    const row = input.closest(".order-row");
    row.querySelector(".order-subtotal").textContent = formatMoney(
      Number(state.orderItems[index].product.price) * quantity,
    );
    updateOrderTotal();
  });

  // 调拨弹窗内的商品增删
  $("transferItems").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-transfer-remove]");
    if (!button) return;
    state.transferItems.splice(Number(button.dataset.transferRemove), 1);
    renderTransferItems();
  });

  $("transferItems").addEventListener("input", (event) => {
    const input = event.target.closest("input[data-transfer-index]");
    if (!input) return;
    const index = Number(input.dataset.transferIndex);
    state.transferItems[index].quantity = Math.max(1, Number(input.value) || 1);
  });

  // ESC 关闭弹窗
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    document.querySelectorAll(".modal-layer").forEach((layer) => {
      if (!layer.hidden) closeModal(layer.id);
    });
  });
}

async function init() {
  bindEvents();

  if (!state.token) {
    $("loginLayer").hidden = false;
    return;
  }

  try {
    // 用 token 换取最新用户信息，顺便验证 token 是否过期。
    state.user = await api("/api/auth/me");
    persistAuth();
    await startApp();
  } catch (error) {
    // 401 已在 api() 中处理；网络错误时提示并显示登录框。
    $("loginLayer").hidden = false;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  init().catch(showError);
});
