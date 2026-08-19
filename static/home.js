/* =========================================================
   ואהבת — יהדות, ניגון ורוח
   ---------------------------------------------------------
   ⚙️  כאן מעדכנים את כל הפרטים המשתנים של האתר:
       טלפון, וואטסאפ, ואירועים על הלוח.
       אין צורך לגעת בשום קובץ אחר.
   ========================================================= */

const CONFIG = {
  /* ⬇️ להחליף למספר האמיתי של נועה (זה מה שמוצג באתר) */
  phoneDisplay: '055-307-8884',

  /* ⬇️ אותו מספר בפורמט בינלאומי: 972 ואז המספר בלי 0 מוביל.
        לדוגמה: 0501234567  ->  972501234567                  */
  whatsappNumber: '972553078884',

  /* ההודעה שנפתחת אוטומטית בוואטסאפ כשלוחצים על כפתור */
  whatsappGreeting: 'היי נועה! הגעתי מהאתר של ואהבת ואשמח לשמוע עוד 🙂',

  /* ⬇️ כתובת המקום — ממנה נבנים לבד כל קישורי הניווט (Waze ומפות גוגל) */
  address: 'עוזיאל 50, רמת גן',

  /* קישורי "בואו לערב הקרוב" (data-event) מוזרקים ישירות ב-home.html
     דרך {{ url_for('register') }} - אין צורך להגדיר אותם כאן. */
};

/* =========================================================
   📌 הלוח — המערכת השבועית
   ---------------------------------------------------------
   כל אובייקט = יום קבוע, עם רשימת המפגשים באותו ערב.
   שדות בכל יום:
     day   — שם היום (למשל 'יום ראשון')
     items — רשימת המפגשים, כל אחד עם:
       time  — שעה
       title — שם המפגש
       desc  — פרטים נוספים (אופציונלי — למשל שם המעביר/ה)
   ========================================================= */

const SCHEDULE = [
  {
    day: 'יום ראשון',
    items: [
      { time: '19:30', title: 'קפה ופינוקים' },
      { time: '20:00', title: 'חדר כושר של הנפש', desc: 'ארז רומס' },
      { time: '21:00', title: 'תניא', desc: 'הרב דרור חזן' },
    ],
  },
  {
    day: 'יום שלישי',
    items: [
      { time: '19:30', title: 'קפה ופינוקים' },
      { time: '20:00', title: 'לשוב אל עצמי', desc: 'נריה פנדל' },
      { time: '21:00', title: 'מחפשים כיוון — לומדים ר\' נחמן', desc: 'הרב עידו גנירם' },
    ],
  },
  {
    day: 'יום חמישי',
    items: [
      { time: '19:30', title: 'קפה ופינוקים' },
      { time: '20:00', title: 'פותחים סופ"ש — פרשת שבוע', desc: 'הרב דרור חזן' },
      { time: '21:00', title: 'חמישי ניגון ב\'ואהבת\'', desc: 'ג\'אם מוזיקלי, בירה קרה, דיבורים מהלב' },
    ],
  },
];

/* =========================================================
   מכאן והלאה — קוד האתר. אין צורך לערוך.
   ========================================================= */

(function () {
  'use strict';

  /* ---------- WhatsApp + phone links ---------- */
  const waHref =
    'https://wa.me/' + CONFIG.whatsappNumber +
    '?text=' + encodeURIComponent(CONFIG.whatsappGreeting);

  document.querySelectorAll('[data-wa]').forEach(function (el) {
    el.href = waHref;
    el.target = '_blank';
    el.rel = 'noopener';
  });

  document.querySelectorAll('[data-tel]').forEach(function (el) {
    el.href = 'tel:+' + CONFIG.whatsappNumber;
  });

  /* ---------- Navigation (Waze / Google Maps) + event links ---------- */
  const external = function (selector, href) {
    document.querySelectorAll(selector).forEach(function (el) {
      el.href = href;
      el.target = '_blank';
      el.rel = 'noopener';
    });
  };

  external(
    '[data-waze]',
    'https://waze.com/ul?q=' + encodeURIComponent(CONFIG.address) + '&navigate=yes'
  );
  external(
    '[data-maps]',
    'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent(CONFIG.address)
  );
  document.querySelectorAll('[data-tel-display]').forEach(function (el) {
    el.textContent = CONFIG.phoneDisplay;
  });

  /* ---------- Weekly schedule board ---------- */
  const grid = document.getElementById('boardGrid');
  if (grid) {
    if (SCHEDULE.length === 0) {
      grid.innerHTML =
        '<p class="board-note">הלוח מתחדש ממש בקרוב — שווה לחזור לבדוק 🙂</p>';
    } else {
      SCHEDULE.forEach(function (day, i) {
        const card = document.createElement('article');
        card.className = 'day-card reveal';
        card.style.animationDelay = (i % 3) * 0.12 + 's';

        const h = document.createElement('h3');
        h.className = 'day-card-title';
        h.textContent = day.day;
        card.appendChild(h);

        const list = document.createElement('div');
        list.className = 'day-card-list';

        day.items.forEach(function (ev) {
          const row = document.createElement('div');
          row.className = 'day-row';

          const time = document.createElement('span');
          time.className = 'day-time';
          time.textContent = ev.time;

          const body = document.createElement('div');
          body.className = 'day-row-body';

          const title = document.createElement('strong');
          title.textContent = ev.title;
          body.appendChild(title);

          if (ev.desc) {
            const desc = document.createElement('span');
            desc.className = 'day-desc';
            desc.textContent = ev.desc;
            body.appendChild(desc);
          }

          row.append(time, body);
          list.appendChild(row);
        });

        card.appendChild(list);
        grid.appendChild(card);
      });
    }
  }

  /* ---------- Mobile nav ---------- */
  const navToggle = document.getElementById('navToggle');
  const mainNav = document.getElementById('mainNav');
  if (navToggle && mainNav) {
    navToggle.addEventListener('click', function () {
      const open = mainNav.classList.toggle('open');
      navToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      navToggle.setAttribute('aria-label', open ? 'סגירת תפריט' : 'פתיחת תפריט');
    });
    mainNav.querySelectorAll('a').forEach(function (a) {
      a.addEventListener('click', function () {
        mainNav.classList.remove('open');
        navToggle.setAttribute('aria-expanded', 'false');
        navToggle.setAttribute('aria-label', 'פתיחת תפריט');
      });
    });
  }

  /* ---------- Header shadow on scroll ---------- */
  const header = document.querySelector('.site-header');
  const onScroll = function () {
    header.classList.toggle('scrolled', window.scrollY > 10);
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  /* ---------- Active nav link ---------- */
  const sections = document.querySelectorAll('main section[id]');
  const navLinks = document.querySelectorAll('.main-nav > a:not(.btn)');
  if ('IntersectionObserver' in window && sections.length) {
    const sectionObserver = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            navLinks.forEach(function (a) {
              a.classList.toggle(
                'active',
                a.getAttribute('href') === '#' + entry.target.id
              );
            });
          }
        });
      },
      { rootMargin: '-40% 0px -55% 0px' }
    );
    sections.forEach(function (s) { sectionObserver.observe(s); });
  }

  /* ---------- Reveal on scroll ---------- */
  const reveals = document.querySelectorAll('.reveal');
  if ('IntersectionObserver' in window) {
    const revealObserver = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add('visible');
            revealObserver.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: '0px 0px -40px 0px' }
    );
    reveals.forEach(function (el) { revealObserver.observe(el); });
  } else {
    reveals.forEach(function (el) { el.classList.add('visible'); });
  }

  /* ---------- Contact form -> WhatsApp ---------- */
  const form = document.getElementById('contactForm');
  const status = document.getElementById('formStatus');
  if (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();

      const name = form.fname.value.trim();
      const phone = form.fphone.value.trim();
      const interest = form.finterest.value;
      const back = form.querySelector('input[name="fback"]:checked').value;
      const msg = form.fmsg.value.trim();

      const invalid = [];
      [form.fname, form.fphone].forEach(function (input) {
        input.classList.remove('error');
        input.removeAttribute('aria-invalid');
      });
      if (!name) invalid.push(form.fname);
      if (!phone || phone.replace(/\D/g, '').length < 9) invalid.push(form.fphone);
      if (invalid.length) {
        invalid.forEach(function (input) {
          input.classList.add('error');
          input.setAttribute('aria-invalid', 'true');
        });
        status.textContent = 'רגע לפני — חסר שם או טלפון תקין 🙂';
        status.style.color = '#B3541E';
        invalid[0].focus();
        return;
      }

      const lines = [
        'היי נועה! מילאתי את הטופס באתר של ואהבת:',
        'שם: ' + name,
        'טלפון: ' + phone,
        'מעניין אותי: ' + interest,
        'איך לחזור אליי: ' + back,
      ];
      if (msg) lines.push('הודעה: ' + msg);

      const url =
        'https://wa.me/' + CONFIG.whatsappNumber +
        '?text=' + encodeURIComponent(lines.join('\n'));
      window.open(url, '_blank', 'noopener');

      status.style.color = '';
      status.textContent = 'מעולה! נפתחה הודעת וואטסאפ מוכנה — נשאר רק לשלוח 🧡 ';
      var fallback = document.createElement('a');
      fallback.href = url;
      fallback.target = '_blank';
      fallback.rel = 'noopener';
      fallback.textContent = 'לא נפתח? לחצו כאן';
      status.appendChild(fallback);
      form.reset();
    });
  }

  /* ---------- Footer year ---------- */
  const year = document.getElementById('year');
  if (year) year.textContent = new Date().getFullYear();
})();
