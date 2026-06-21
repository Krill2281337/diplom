const FAVORITES_KEY = 'yoly-paly-favorites';

function getFavorites() {
  try {
    return JSON.parse(localStorage.getItem(FAVORITES_KEY)) || [];
  } catch (e) {
    return [];
  }
}

function saveFavorites(items) {
  localStorage.setItem(FAVORITES_KEY, JSON.stringify(items));
}

function formatPrice(value) {
  return new Intl.NumberFormat('ru-RU').format(value) + ' ₽';
}

function parseDateLocal(value) {
  const [year, month, day] = value.split('-').map(Number);
  return new Date(year, month - 1, day);
}

function formatDateRu(value) {
  if (!value) return '';
  return parseDateLocal(value).toLocaleDateString('ru-RU');
}

function toISODateLocal(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function dateRangeOverlaps(startA, endA, startB, endB) {
  return startA < endB && endA > startB;
}

function getBusyRange(cottage, checkin, checkout) {
  const ranges = (window.occupiedRanges || {})[cottage] || [];
  if (!cottage || !checkin || !checkout) return null;

  const start = parseDateLocal(checkin);
  const end = parseDateLocal(checkout);

  return ranges.find(range => {
    const busyStart = parseDateLocal(range.check_in);
    const busyEnd = parseDateLocal(range.check_out);
    return dateRangeOverlaps(start, end, busyStart, busyEnd);
  }) || null;
}

function setAvailabilityMessage(type, text) {
  const message = document.getElementById('availabilityMessage');
  if (!message) return;
  message.classList.remove('ok', 'error');
  if (type) message.classList.add(type);
  message.textContent = text;
}

function updateGuestsLimit() {
  const roomMap = window.roomPrices || {};
  const cottage = document.getElementById('cottageSelect').value;
  const guestsInput = document.getElementById('guestsCount');
  if (!guestsInput || !roomMap[cottage]) return;

  const capacity = Number(roomMap[cottage].capacity || 5);
  guestsInput.max = String(capacity);
  if (Number(guestsInput.value) > capacity) guestsInput.value = String(capacity);
}

function openBookingModal(cottageName = '') {
  const modal = document.getElementById('bookingModal');
  const select = document.getElementById('cottageSelect');
  if (select && cottageName) select.value = cottageName;
  updateGuestsLimit();
  if (modal) {
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
  }
  updateBookingSummary();
}

function closeModal() {
  const modal = document.getElementById('bookingModal');
  if (modal) {
    modal.classList.remove('active');
    document.body.style.overflow = '';
  }
}

function calculatePreviewTotal() {
  const roomMap = window.roomPrices || {};
  const cottage = document.getElementById('cottageSelect').value;
  const checkin = document.getElementById('checkinDate').value;
  const checkout = document.getElementById('checkoutDate').value;
  const guests = Number(document.getElementById('guestsCount').value || 1);
  const extras = [...document.querySelectorAll('input[name="extras"]:checked')].map(i => i.value);

  if (!roomMap[cottage] || !checkin || !checkout) {
    setAvailabilityMessage('', 'Выберите вариант размещения и даты, чтобы проверить доступность.');
    return { nights: 0, total: 0, ready: false, error: 'Выберите даты' };
  }

  const start = parseDateLocal(checkin);
  const end = parseDateLocal(checkout);
  const diff = Math.round((end - start) / (1000 * 60 * 60 * 24));
  if (diff <= 0) {
    setAvailabilityMessage('error', 'Дата выезда должна быть позже даты заезда.');
    return { nights: 0, total: 0, ready: false, error: 'Проверьте даты' };
  }

  if (guests > roomMap[cottage].capacity) {
    setAvailabilityMessage('error', `Максимум для выбранного варианта: ${roomMap[cottage].capacity} гост.`);
    return { nights: diff, total: 0, ready: false, error: `Максимум: ${roomMap[cottage].capacity} гост.` };
  }

  const busyRange = getBusyRange(cottage, checkin, checkout);
  if (busyRange) {
    setAvailabilityMessage(
      'error',
      `Выбранный вариант занят с ${formatDateRu(busyRange.check_in)} по ${formatDateRu(busyRange.check_out)}. Выберите другие даты.`
    );
    return { nights: diff, total: 0, ready: false, error: 'Даты заняты' };
  }

  let total = 0;
  for (let i = 0; i < diff; i += 1) {
    const day = new Date(start);
    day.setDate(start.getDate() + i);
    const weekday = day.getDay();
    const isWeekend = weekday === 5 || weekday === 6 || weekday === 0;
    total += isWeekend ? roomMap[cottage].weekend_price : roomMap[cottage].weekday_price;
  }

  const serviceMap = window.extraServices || {};
  extras.forEach(code => {
    const service = serviceMap[code];
    if (!service) return;
    const price = Number(service.price || 0);
    if (service.price_type === 'fixed') total += price;
    if (service.price_type === 'per_guest_night') total += guests * diff * price;
  });

  setAvailabilityMessage('ok', 'Выбранные даты свободны для предварительной заявки.');
  return { nights: diff, total, ready: true };
}

function updateBookingSummary() {
  updateGuestsLimit();
  const result = calculatePreviewTotal();
  const nightsPreview = document.getElementById('nightsPreview');
  const pricePreview = document.getElementById('pricePreview');

  if (!nightsPreview || !pricePreview) return;

  nightsPreview.textContent = result.nights ? `${result.nights}` : '—';
  pricePreview.textContent = result.ready ? formatPrice(result.total) : result.error;
}

function applyFilters() {
  const searchValue = document.getElementById('searchInput').value.trim().toLowerCase();
  const capacityValue = document.getElementById('capacityFilter').value;
  const showFavoritesOnly = document.getElementById('showFavorites').dataset.mode === 'favorites';
  const favorites = getFavorites();
  const cards = [...document.querySelectorAll('.cottage-card')];

  let visibleCount = 0;

  cards.forEach(card => {
    const name = card.dataset.name.toLowerCase();
    const capacity = Number(card.dataset.capacity);
    const searchableText = `${name} ${card.textContent}`.toLowerCase();
    const matchesSearch = searchableText.includes(searchValue);
    const matchesCapacity = capacityValue === 'all' || capacity >= Number(capacityValue);
    const matchesFavorite = !showFavoritesOnly || favorites.includes(card.dataset.name);
    const visible = matchesSearch && matchesCapacity && matchesFavorite;

    card.classList.toggle('hidden', !visible);
    if (visible) visibleCount += 1;
  });

  document.getElementById('resultsCount').textContent = `Показано вариантов: ${visibleCount}`;
}

function syncFavoriteButtons() {
  const favorites = getFavorites();
  document.querySelectorAll('.cottage-card').forEach(card => {
    const active = favorites.includes(card.dataset.name);
    const button = card.querySelector('.favorite-btn');
    if (!button) return;
    button.classList.toggle('active', active);
    button.innerHTML = active
      ? '<i class="fa-solid fa-heart"></i>'
      : '<i class="fa-regular fa-heart"></i>';
  });
}

function setupFavorites() {
  document.querySelectorAll('.favorite-btn').forEach(button => {
    button.addEventListener('click', () => {
      const card = button.closest('.cottage-card');
      const favoriteName = card.dataset.name;
      const favorites = getFavorites();
      const index = favorites.indexOf(favoriteName);

      if (index >= 0) favorites.splice(index, 1);
      else favorites.push(favoriteName);

      saveFavorites(favorites);
      syncFavoriteButtons();
      applyFilters();
    });
  });
}

function setupFilters() {
  document.getElementById('searchInput').addEventListener('input', applyFilters);
  document.getElementById('capacityFilter').addEventListener('change', applyFilters);

  const favoritesToggle = document.getElementById('showFavorites');
  favoritesToggle.dataset.mode = 'all';
  favoritesToggle.addEventListener('click', () => {
    favoritesToggle.dataset.mode = favoritesToggle.dataset.mode === 'all' ? 'favorites' : 'all';
    favoritesToggle.textContent = favoritesToggle.dataset.mode === 'favorites'
      ? 'Показать все варианты'
      : 'Показать только избранное';
    applyFilters();
  });
}

function setupMenu() {
  const menuButton = document.getElementById('menuToggle');
  const nav = document.getElementById('siteNav');
  menuButton.addEventListener('click', () => nav.classList.toggle('open'));

  nav.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', () => nav.classList.remove('open'));
  });
}

function setupBookingButtons() {
  document.querySelectorAll('.cc-book-btn').forEach(button => {
    button.addEventListener('click', () => openBookingModal(button.dataset.cottage || ''));
  });

  document.getElementById('bookNow').addEventListener('click', () => openBookingModal());
  document.getElementById('modalClose').addEventListener('click', closeModal);

  document.getElementById('bookingModal').addEventListener('click', (event) => {
    if (event.target.id === 'bookingModal') closeModal();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      closeModal();
      closeGalleryModal();
    }
  });
}

function handleBooking(event) {
  const cottage = document.getElementById('cottageSelect').value;
  const checkin = document.getElementById('checkinDate').value;
  const checkout = document.getElementById('checkoutDate').value;
  const guests = document.getElementById('guestsCount').value;
  const name = document.getElementById('guestName').value;
  const phone = document.getElementById('guestPhone').value;
  const consent = document.querySelector('input[name="personal_data_consent"]').checked;
  const preview = calculatePreviewTotal();

  if (!cottage || !checkin || !checkout || !guests || !name || !phone) {
    event.preventDefault();
    alert('Пожалуйста, заполните все обязательные поля формы.');
    return;
  }

  if (!consent) {
    event.preventDefault();
    alert('Необходимо согласие на обработку персональных данных.');
    return;
  }

  if (!preview.ready) {
    event.preventDefault();
    alert(preview.error || 'Проверьте параметры бронирования.');
  }
}

function setupActiveNav() {
  const links = [...document.querySelectorAll('.nav a')];
  const sections = links
    .map(link => document.querySelector(link.getAttribute('href')))
    .filter(Boolean);

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      links.forEach(link => {
        link.classList.toggle('active', link.getAttribute('href') === `#${entry.target.id}`);
      });
    });
  }, { threshold: 0.35 });

  sections.forEach(section => observer.observe(section));
}

function openGalleryModal(title, imageSrc) {
  const modal = document.getElementById('galleryModal');
  const preview = document.getElementById('galleryPreviewText');
  preview.innerHTML = `
    <img src="${imageSrc}" alt="${title}">
    <div class="gallery-caption">
      <h3>${title}</h3>
      <p>Фотография территории базы отдыха «Ёлы-Палы».</p>
    </div>
  `;
  modal.classList.add('active');
  document.body.style.overflow = 'hidden';
}

function closeGalleryModal() {
  const modal = document.getElementById('galleryModal');
  if (modal.classList.contains('active')) {
    modal.classList.remove('active');
    if (!document.getElementById('bookingModal').classList.contains('active')) {
      document.body.style.overflow = '';
    }
  }
}

function setupGallery() {
  document.querySelectorAll('.gallery-tile').forEach(tile => {
    tile.addEventListener('click', () => openGalleryModal(tile.dataset.title || 'Фото', tile.dataset.image || ''));
  });
  document.getElementById('galleryClose').addEventListener('click', closeGalleryModal);
  document.getElementById('galleryModal').addEventListener('click', (event) => {
    if (event.target.id === 'galleryModal') closeGalleryModal();
  });
}

function setupBookingInputs() {
  const today = toISODateLocal(new Date());
  const checkin = document.getElementById('checkinDate');
  const checkout = document.getElementById('checkoutDate');
  checkin.min = today;
  checkout.min = today;

  checkin.addEventListener('change', () => {
    if (checkin.value) {
      const start = parseDateLocal(checkin.value);
      start.setDate(start.getDate() + 1);
      const minCheckout = toISODateLocal(start);
      checkout.min = minCheckout;
      if (!checkout.value || checkout.value <= checkin.value) {
        checkout.value = checkout.min;
      }
    }
    updateBookingSummary();
  });

  ['change', 'input'].forEach(eventName => {
    document.getElementById('cottageSelect').addEventListener(eventName, updateBookingSummary);
    document.getElementById('checkoutDate').addEventListener(eventName, updateBookingSummary);
    document.getElementById('guestsCount').addEventListener(eventName, updateBookingSummary);
  });

  document.querySelectorAll('input[name="extras"]').forEach(item => {
    item.addEventListener('change', updateBookingSummary);
  });
}

document.addEventListener('DOMContentLoaded', () => {
  setupMenu();
  setupFilters();
  setupFavorites();
  syncFavoriteButtons();
  applyFilters();
  setupBookingButtons();
  setupActiveNav();
  setupGallery();
  setupBookingInputs();
  updateBookingSummary();

  document.getElementById('bookingForm').addEventListener('submit', handleBooking);
});
