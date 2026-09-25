

from flask import Flask, request, redirect, url_for, flash, render_template_string, jsonify
from datetime import datetime, timedelta
from pathlib import Path
import os
import json
import re
from zoneinfo import ZoneInfo
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "unisex-salon-secret-key")

# =========================================================
# CONFIGURATION
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

OPEN_HOUR = 10   # 10:00 AM
CLOSE_HOUR = 21  # 9:00 PM
MAX_BOOKING_DAYS = 7
INDIA_TIME_ZONE = ZoneInfo("Asia/Kolkata")


# =========================================================
# =========================================================
# DATABASE + GOOGLE SHEETS
# =========================================================

GOOGLE_SCRIPT_URL = os.getenv("GOOGLE_SCRIPT_URL", "").strip()
OWNER_EMAIL = os.getenv("OWNER_EMAIL", "valorasalon@gmail.com")


def validate_appointment_window(appointment_date, appointment_time):
    try:
        selected_date = datetime.strptime(appointment_date, "%Y-%m-%d").date()
        selected_time = datetime.strptime(appointment_time, "%H:%M").time()
    except ValueError:
        return "Please choose a valid appointment date and time."

    now = datetime.now(INDIA_TIME_ZONE)
    today = now.date()
    last_date = today + timedelta(days=MAX_BOOKING_DAYS)
    if not today <= selected_date <= last_date:
        return f"Appointments can be booked only for today through the next {MAX_BOOKING_DAYS} days."

    start_time = datetime.strptime("10:00", "%H:%M").time()
    end_time = datetime.strptime("20:30", "%H:%M").time()
    if not start_time <= selected_time <= end_time:
        return "Appointments are available from 10:00 AM to 8:30 PM."
    if selected_date == today and selected_time <= now.time():
        return "That time has already passed. Please choose a later time."
    return None


def call_google_script(method, payload=None, query=None):
    if not GOOGLE_SCRIPT_URL or not GOOGLE_SCRIPT_URL.endswith("/exec"):
        raise RuntimeError("GOOGLE_SCRIPT_URL must be the deployed Apps Script /exec URL")

    url = GOOGLE_SCRIPT_URL
    if query:
        url = f"{url}?{urlencode(query)}"
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"} if body else {}
    request = Request(url, data=body, headers=headers, method=method)

    try:
        with urlopen(request, timeout=25) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        print("GOOGLE SCRIPT ERROR:", repr(error))
        raise RuntimeError("Booking service is temporarily unavailable") from error

    if not isinstance(result, dict):
        raise RuntimeError("Booking service returned an invalid response")
    return result


# =========================================================

# =========================================================
# SALON STATUS
# =========================================================

def get_salon_status():
    india_now = datetime.now(INDIA_TIME_ZONE)
    current_hour = india_now.hour

    if OPEN_HOUR <= current_hour < CLOSE_HOUR:
        return {
            "open": True,
            "text": "OPEN NOW",
            "description": "We're open until 9:00 PM IST"
        }

    return {
        "open": False,
        "text": "CLOSED",
        "description": "Open daily from 10:00 AM IST"
    }


# =========================================================
# SERVICES
# =========================================================

MEN_SERVICES = [
    {
        "name": "Classic Haircut",
        "description": "Precision cut with styling",
        "price": 299,
        "icon": "✂️"
    },
    {
        "name": "Premium Haircut",
        "description": "Cut, wash, massage & styling",
        "price": 499,
        "icon": "💇"
    },
    {
        "name": "Beard Styling",
        "description": "Shape, trim & finishing",
        "price": 199,
        "icon": "🧔"
    },
    {
        "name": "Hair + Beard Combo",
        "description": "Complete grooming experience",
        "price": 599,
        "icon": "✨"
    },
    {
        "name": "Hair Spa",
        "description": "Deep nourishment & relaxation",
        "price": 799,
        "icon": "🧖"
    },
    {
        "name": "Hair Coloring",
        "description": "Professional color treatment",
        "price": 999,
        "icon": "🎨"
    }
]

WOMEN_SERVICES = [
    {
        "name": "Women's Haircut",
        "description": "Modern cut with professional styling",
        "price": 599,
        "icon": "✂️"
    },
    {
        "name": "Women's Hair Spa",
        "description": "Relaxing nourishment treatment",
        "price": 899,
        "icon": "🧖"
    },
    {
        "name": "Global Hair Color",
        "description": "Premium full hair coloring",
        "price": 1999,
        "icon": "🎨"
    },
    {
        "name": "Highlights",
        "description": "Beautiful customized highlights",
        "price": 1499,
        "icon": "✨"
    },
    {
        "name": "Keratin Treatment",
        "description": "Smooth and glossy finish",
        "price": 2499,
        "icon": "💎"
    },
    {
        "name": "Bridal Styling",
        "description": "Elegant event & bridal styling",
        "price": 2999,
        "icon": "👰"
    }
]

ALL_SERVICES = MEN_SERVICES + WOMEN_SERVICES
SERVICE_PRICES = {
    service["name"]: service["price"]
    for service in ALL_SERVICES
}

PAYMENT_OPTIONS = [
    "UPI",
    "Pay at Shop"
]


# =========================================================
# COMPLETE SINGLE-PAGE HTML
# =========================================================

INDEX_HTML = r"""
<!DOCTYPE html>
<html lang="en" class="scroll-smooth">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <title>VELORA | Unisex Hair Studio</title>

    <script src="https://cdn.tailwindcss.com"></script>

    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    fontFamily: {
                        sans: ['Inter', 'sans-serif'],
                        display: ['Playfair Display', 'serif']
                    },
                    colors: {
                        gold: '#C9A227',
                        cream: '#F8F5EF',
                        charcoal: '#181818'
                    }
                }
            }
        }
    </script>

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>

    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Playfair+Display:wght@500;600;700&display=swap"
          rel="stylesheet">

    <style>

        * {
            box-sizing: border-box;
        }

        body {
            font-family: 'Inter', sans-serif;
        }

        .display-font {
            font-family: 'Playfair Display', serif;
        }

        .gold-gradient {
            background: linear-gradient(
                135deg,
                #b88a18,
                #e6c65c,
                #a87d16
            );
        }

        .hero-gradient {
            background:
                radial-gradient(
                    circle at 85% 20%,
                    rgba(201,162,39,0.16),
                    transparent 28%
                ),
                radial-gradient(
                    circle at 15% 80%,
                    rgba(201,162,39,0.10),
                    transparent 25%
                );
        }

        .glass {
            backdrop-filter: blur(18px);
            -webkit-backdrop-filter: blur(18px);
        }

        .glass-panel {
            background: rgba(255, 255, 255, .56);
            border: 1px solid rgba(255, 255, 255, .72);
            box-shadow: 0 24px 70px rgba(56, 42, 18, .12);
            backdrop-filter: blur(22px);
            -webkit-backdrop-filter: blur(22px);
        }

        .hero-photo {
            position: relative;
            isolation: isolate;
        }

        .hero-photo::after {
            content: "";
            position: absolute;
            inset: 0;
            z-index: -1;
            background: linear-gradient(135deg, rgba(255,255,255,.05), rgba(201,162,39,.42));
        }

        .logo-button {
            transition: transform .25s ease, filter .25s ease;
        }

        .logo-button:hover {
            transform: translateY(-2px) rotate(-3deg);
            filter: drop-shadow(0 10px 14px rgba(201,162,39,.28));
        }

        .reveal {
            animation: reveal .7s ease both;
        }

        @keyframes reveal {
            from { opacity: 0; transform: translateY(14px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .service-card {
            transition: all .25s ease;
        }

        .service-card:hover {
            transform: translateY(-6px);
        }

        .time-slot {
            transition: transform .2s ease, background-color .2s ease;
        }

        .time-slot:hover {
            transform: translateY(-2px);
        }

        .time-slot.selected {
            background: #181818;
            color: white;
        }

        .slot-panel {
            max-height: 0;
            overflow: hidden;
            opacity: 0;
            transition: max-height .35s ease, opacity .25s ease;
        }

        .slot-panel.open {
            max-height: 34rem;
            opacity: 1;
        }

        .salon-chair {
            transition: transform .3s ease;
        }

        .salon-chair:hover {
            transform: translateY(-5px);
        }

        .shine {
            position: relative;
            overflow: hidden;
        }

        .shine::after {
            content: "";
            position: absolute;
            top: 0;
            left: -120%;
            width: 60%;
            height: 100%;
            transform: skewX(-20deg);
            background: linear-gradient(
                90deg,
                transparent,
                rgba(255,255,255,.35),
                transparent
            );
            transition: .7s;
        }

        .shine:hover::after {
            left: 140%;
        }

        .status-pulse {
            animation: pulseStatus 2s infinite;
        }

        @keyframes pulseStatus {
            0%, 100% {
                box-shadow: 0 0 0 0 rgba(34,197,94,.35);
            }

            50% {
                box-shadow: 0 0 0 8px rgba(34,197,94,0);
            }
        }

        .closed-pulse {
            animation: pulseClosed 2s infinite;
        }

        @keyframes pulseClosed {
            0%, 100% {
                box-shadow: 0 0 0 0 rgba(239,68,68,.30);
            }

            50% {
                box-shadow: 0 0 0 8px rgba(239,68,68,0);
            }
        }

        .mobile-menu {
            display: none;
        }

        .mobile-menu.active {
            display: block;
        }

    </style>
</head>


<body class="bg-[#F8F5EF] text-[#181818]">


<!-- =====================================================
     NAVBAR
===================================================== -->

<header class="sticky top-0 z-50 border-b border-black/10 dark:border-white/10
               bg-[#F8F5EF]/90 dark:bg-[#111111]/90 glass">

    <div class="max-w-7xl mx-auto px-5 lg:px-8">

        <div class="h-20 flex items-center justify-between">

            <!-- LOGO -->

            <a href="#home" class="logo-button flex items-center gap-3" aria-label="Velora home">

                <div class="w-11 h-11 rounded-full gold-gradient
                            flex items-center justify-center
                            text-white font-bold text-xl shadow-lg">
                    V
                </div>

                <div>
                    <div class="display-font text-xl font-bold tracking-wide">
                        VELORA
                    </div>

                    <div class="text-[9px] tracking-[.35em] opacity-60">
                        HAIR STUDIO
                    </div>
                </div>

            </a>


            <!-- DESKTOP NAV -->

            <nav class="hidden md:flex items-center gap-8 text-sm font-medium">

                <a href="#home"
                   class="hover:text-[#C9A227] transition">
                    Home
                </a>

                <a href="#services"
                   class="hover:text-[#C9A227] transition">
                    Services
                </a>

                <a href="#about"
                   class="hover:text-[#C9A227] transition">
                    About
                </a>

                <a href="#booking"
                   class="hover:text-[#C9A227] transition">
                    Contact
                </a>

            </nav>


            <!-- RIGHT -->

            <div class="flex items-center gap-3">

                <!-- BOOK BUTTON -->

                <a href="#booking"
                   class="hidden sm:flex px-5 py-2.5 rounded-full
                          gold-gradient text-white font-semibold
                          text-sm shadow-lg hover:scale-105 transition">

                    Book Appointment

                </a>


                <!-- MOBILE MENU -->

                <button
                    onclick="toggleMobileMenu()"
                    class="md:hidden w-10 h-10 rounded-full border
                           border-black/10 dark:border-white/10">

                    ☰

                </button>

            </div>

        </div>


        <!-- MOBILE NAV -->

        <div id="mobileMenu"
             class="mobile-menu md:hidden pb-5">

            <div class="flex flex-col gap-4 text-sm">

                <a href="#home"
                   onclick="closeMobileMenu()">
                    Home
                </a>

                <a href="#services"
                   onclick="closeMobileMenu()">
                    Services
                </a>

                <a href="#about"
                   onclick="closeMobileMenu()">
                    About
                </a>

                <a href="#booking"
                   onclick="closeMobileMenu()">
                    Book Appointment
                </a>

            </div>

        </div>

    </div>

</header>



<!-- =====================================================
     FLASH MESSAGES
===================================================== -->

{% with messages = get_flashed_messages(with_categories=true) %}

    {% if messages %}

        <div class="fixed top-24 right-5 z-[100] space-y-3">

            {% for category, message in messages %}

                <div
                    class="max-w-sm rounded-2xl px-5 py-4 shadow-2xl
                    {% if category == 'success' %}
                        bg-green-600 text-white
                    {% else %}
                        bg-red-600 text-white
                    {% endif %}">

                    <div class="font-semibold">
                        {{ message }}
                    </div>

                </div>

            {% endfor %}

        </div>

    {% endif %}

{% endwith %}



<!-- =====================================================
     HERO
===================================================== -->

<section id="home"
         class="hero-gradient min-h-[calc(100vh-80px)]
          flex items-center reveal">

    <div class="max-w-7xl mx-auto px-5 lg:px-8
                py-20 lg:py-24 w-full">

        <div class="grid lg:grid-cols-2 gap-14 items-center">


            <!-- LEFT -->

            <div>

                <!-- STATUS -->

                {% if status.open %}

                    <div class="inline-flex items-center gap-2
                                px-4 py-2 rounded-full
                                bg-green-100 dark:bg-green-900/30
                                text-green-700 dark:text-green-300
                                text-sm font-semibold mb-7
                                status-pulse">

                        <span class="w-2.5 h-2.5 rounded-full bg-green-500"></span>

                        OPEN NOW

                        <span class="opacity-60">
                            • {{ status.description }}
                        </span>

                    </div>

                {% else %}

                    <div class="inline-flex items-center gap-2
                                px-4 py-2 rounded-full
                                bg-red-100 dark:bg-red-900/30
                                text-red-700 dark:text-red-300
                                text-sm font-semibold mb-7
                                closed-pulse">

                        <span class="w-2.5 h-2.5 rounded-full bg-red-500"></span>

                        CLOSED

                        <span class="opacity-60">
                            • {{ status.description }}
                        </span>

                    </div>

                {% endif %}


                <h1 class="display-font text-5xl sm:text-6xl
                           lg:text-7xl leading-[1.05] font-semibold">

                    Your Style.

                    <br>

                    <span class="text-[#C9A227]">
                        Your Statement.
                    </span>

                </h1>


                <p class="mt-7 text-lg leading-8
                          text-black/60 dark:text-white/60
                          max-w-xl">

                    A premium unisex hair studio where modern
                    styling meets personalized care. Walk in
                    looking good. Walk out feeling incredible.

                </p>


                <div class="flex flex-wrap gap-4 mt-9">

                    <a href="#booking"
                       class="shine px-7 py-4 rounded-full
                              gold-gradient text-white
                              font-bold shadow-xl
                              hover:scale-105 transition">

                        Book Your Session →

                    </a>

                    <a href="#services"
                       class="px-7 py-4 rounded-full
                              border border-black/15
                                                            glass-panel
                              font-semibold
                              hover:border-[#C9A227]
                              transition">
                        Explore Services

                    </a>

                </div>


                <!-- MINI STATS -->

                <div class="flex flex-wrap gap-8 mt-12">

                    <div>
                        <div class="text-2xl font-bold">
                            8+
                        </div>

                        <div class="text-sm opacity-50">
                            Years Experience
                        </div>
                    </div>

                    <div>
                        <div class="text-2xl font-bold">
                            5K+
                        </div>

                        <div class="text-sm opacity-50">
                            Happy Clients
                        </div>
                    </div>

                    <div>
                        <div class="text-2xl font-bold">
                            4.9/5
                        </div>

                        <div class="text-sm opacity-50">
                            Client Rating
                        </div>
                    </div>

                </div>

            </div>


            <!-- STUDIO PHOTO -->

            <div class="relative hero-photo">

                <div class="rounded-[2rem] overflow-hidden shadow-2xl
                            border border-white/70
                            glass-panel">

                    <img
                        src="https://images.unsplash.com/photo-1560066984-138dadb4c035?auto=format&fit=crop&w=1200&q=88"
                        alt="Warm Velora hair studio interior"
                        class="w-full h-[28rem] object-cover opacity-95">

                    <div class="absolute inset-x-6 bottom-6 glass-panel rounded-2xl px-5 py-4">
                        <div class="text-xs uppercase tracking-[.25em] text-[#8a6812]">Velora Studio</div>
                        <div class="display-font text-2xl mt-1">A calmer kind of confidence.</div>
                    </div>

                </div>

                <!-- FLOATING CARD -->

                <div class="absolute -bottom-7 -left-5
                            sm:-left-8
                            glass-panel rounded-2xl p-4 shadow-2xl
                            border border-white/70">

                    <div class="flex items-center gap-3">

                        <div class="w-11 h-11 rounded-full
                                    gold-gradient
                                    flex items-center justify-center
                                    text-white">

                            ★

                        </div>

                        <div>

                            <div class="font-bold">
                                Premium Experience
                            </div>

                            <div class="text-xs opacity-50">
                                Style • Care • Confidence
                            </div>

                        </div>

                    </div>

                </div>

            </div>

        </div>

    </div>

</section>



<!-- =====================================================
     SERVICES
===================================================== -->

<section id="services"
         class="py-24 bg-white dark:bg-[#161616] reveal">

    <div class="max-w-7xl mx-auto px-5 lg:px-8">

        <div class="text-center max-w-2xl mx-auto">

            <p class="text-[#C9A227] font-bold tracking-[.25em]
                      text-xs uppercase">
                Our Menu
            </p>

            <h2 class="display-font text-4xl sm:text-5xl
                       font-semibold mt-3">

                Services crafted for you

            </h2>

            <p class="mt-5 opacity-60">
                From everyday grooming to complete transformations,
                choose the experience that fits your style.
            </p>

        </div>


        <!-- TABS -->

        <div class="flex justify-center mt-10">

            <div class="p-1.5 rounded-full
                        bg-black/5 dark:bg-white/5
                        flex">

                <button
                    id="menTab"
                    onclick="showServices('men')"
                    class="service-tab px-7 py-3 rounded-full
                           text-sm font-bold
                           bg-[#181818] text-white
                           dark:bg-white dark:text-black">

                    Men's Services

                </button>

                <button
                    id="womenTab"
                    onclick="showServices('women')"
                    class="service-tab px-7 py-3 rounded-full
                           text-sm font-bold">

                    Women's Services

                </button>

            </div>

        </div>


        <!-- MEN SERVICES -->

        <div id="menServices"
             class="grid sm:grid-cols-2 lg:grid-cols-3
                    gap-5 mt-10">

            {% for service in men_services %}

            <div class="service-card p-6 rounded-3xl
                        border border-black/10
                        dark:border-white/10
                        bg-[#F8F5EF]
                        dark:bg-[#202020]">

                <div class="flex justify-between items-start">

                    <div class="w-12 h-12 rounded-2xl
                                bg-[#C9A227]/10
                                flex items-center justify-center
                                text-xl">

                        {{ service.icon }}

                    </div>

                    <div class="text-xl font-bold text-[#C9A227]">
                        ₹{{ service.price }}
                    </div>

                </div>


                <h3 class="font-bold text-lg mt-5">
                    {{ service.name }}
                </h3>

                <p class="text-sm opacity-50 mt-2">
                    {{ service.description }}
                </p>


                <button
                    onclick="selectService('{{ service.name }}')"
                    class="mt-5 text-sm font-bold
                           text-[#C9A227]
                           hover:underline">

                    Book this service →

                </button>

            </div>

            {% endfor %}

        </div>


        <!-- WOMEN SERVICES -->

        <div id="womenServices"
             class="hidden grid sm:grid-cols-2 lg:grid-cols-3
                    gap-5 mt-10">

            {% for service in women_services %}

            <div class="service-card p-6 rounded-3xl
                        border border-black/10
                        dark:border-white/10
                        bg-[#F8F5EF]
                        dark:bg-[#202020]">

                <div class="flex justify-between items-start">

                    <div class="w-12 h-12 rounded-2xl
                                bg-[#C9A227]/10
                                flex items-center justify-center
                                text-xl">

                        {{ service.icon }}

                    </div>

                    <div class="text-xl font-bold text-[#C9A227]">
                        ₹{{ service.price }}
                    </div>

                </div>


                <h3 class="font-bold text-lg mt-5">
                    {{ service.name }}
                </h3>

                <p class="text-sm opacity-50 mt-2">
                    {{ service.description }}
                </p>


                <button
                    onclick="selectService('{{ service.name }}')"
                    class="mt-5 text-sm font-bold
                           text-[#C9A227]
                           hover:underline">

                    Book this service →

                </button>

            </div>

            {% endfor %}

        </div>

    </div>

</section>



<!-- =====================================================
     ABOUT
===================================================== -->

<section id="about"
         class="py-24 hero-gradient reveal">

    <div class="max-w-7xl mx-auto px-5 lg:px-8">

        <div class="grid lg:grid-cols-2 gap-14 items-center">


            <div>

                <p class="text-[#C9A227] font-bold
                          tracking-[.25em] text-xs uppercase">

                    Why Velora

                </p>

                <h2 class="display-font text-4xl sm:text-5xl
                           font-semibold mt-4">

                    More than a haircut.
                    <span class="text-[#C9A227]">
                        It's your moment.
                    </span>

                </h2>

                <p class="mt-6 opacity-60 leading-8">

                    Our studio is designed around one simple idea:
                    premium grooming should feel personal,
                    comfortable and effortless.

                </p>


                <div class="grid sm:grid-cols-2 gap-5 mt-9">

                    <div class="p-5 rounded-2xl
                                bg-white/70 dark:bg-white/5
                                border border-black/5
                                dark:border-white/10">

                        <div class="text-2xl">
                            ✨
                        </div>

                        <div class="font-bold mt-3">
                            Premium Products
                        </div>

                        <p class="text-sm opacity-50 mt-1">
                            Professional products selected
                            for quality results.
                        </p>

                    </div>


                    <div class="p-5 rounded-2xl
                                bg-white/70 dark:bg-white/5
                                border border-black/5
                                dark:border-white/10">

                        <div class="text-2xl">
                            💇
                        </div>

                        <div class="font-bold mt-3">
                            Expert Stylists
                        </div>

                        <p class="text-sm opacity-50 mt-1">
                            Experienced professionals
                            focused on your style.
                        </p>

                    </div>

                </div>

            </div>


            <div class="grid grid-cols-2 gap-4">

                <div class="rounded-3xl overflow-hidden bg-white dark:bg-[#202020] shadow-lg">
                    <img src="https://images.unsplash.com/photo-1621605815971-fbc98d665033?auto=format&fit=crop&w=700&q=85"
                         alt="Arjun, senior barber"
                         class="w-full h-52 object-cover">
                    <div class="p-4">
                        <div class="font-bold">Arjun</div>
                        <div class="text-xs opacity-50">Senior Barber</div>
                        <div class="text-[#C9A227] text-sm mt-2">★★★★★ <span class="text-black/50 dark:text-white/50">4.9</span></div>
                    </div>
                </div>

                <div class="rounded-3xl overflow-hidden bg-white dark:bg-[#202020] shadow-lg mt-8">
                    <img src="https://images.unsplash.com/photo-1580618672591-eb180b1a973f?auto=format&fit=crop&w=700&q=85"
                         alt="Karan, hair specialist"
                         class="w-full h-52 object-cover">
                    <div class="p-4">
                        <div class="font-bold">Karan</div>
                        <div class="text-xs opacity-50">Hair Specialist</div>
                        <div class="text-[#C9A227] text-sm mt-2">★★★★★ <span class="text-black/50 dark:text-white/50">4.8</span></div>
                    </div>
                </div>

                <div class="rounded-3xl overflow-hidden bg-white dark:bg-[#202020] shadow-lg">
                    <img src="https://images.unsplash.com/photo-1487412720507-e7ab37603c6f?auto=format&fit=crop&w=700&q=85"
                         alt="Riya, senior stylist"
                         class="w-full h-52 object-cover">
                    <div class="p-4">
                        <div class="font-bold">Riya</div>
                        <div class="text-xs opacity-50">Senior Stylist</div>
                        <div class="text-[#C9A227] text-sm mt-2">★★★★★ <span class="text-black/50 dark:text-white/50">5.0</span></div>
                    </div>
                </div>

                <div class="rounded-3xl overflow-hidden bg-white dark:bg-[#202020] shadow-lg mt-8">
                    <img src="https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=700&q=85"
                         alt="Meera, color specialist"
                         class="w-full h-52 object-cover">
                    <div class="p-4">
                        <div class="font-bold">Meera</div>
                        <div class="text-xs opacity-50">Color Specialist</div>
                        <div class="text-[#C9A227] text-sm mt-2">★★★★★ <span class="text-black/50 dark:text-white/50">4.9</span></div>
                    </div>
                </div>

            </div>

        </div>

    </div>

</section>



<!-- =====================================================
     BOOKING
===================================================== -->

<section id="booking"
         class="py-24 bg-white dark:bg-[#161616] reveal">

    <div class="max-w-5xl mx-auto px-5 lg:px-8">

        <div class="text-center">

            <p class="text-[#C9A227] font-bold
                      tracking-[.25em] text-xs uppercase">

                Reservations

            </p>

            <h2 class="display-font text-4xl sm:text-5xl
                       font-semibold mt-3">

                Reserve your chair

            </h2>

            <p class="opacity-60 mt-4">
                Choose your preferred service, stylist and time.
            </p>

        </div>


        <form id="bookingForm" action="{{ url_for('book') }}"
              method="POST"
              class="mt-12 p-6 sm:p-9
                     rounded-[2rem]
                     border border-black/10
                     dark:border-white/10
                     glass-panel
                     dark:bg-[#202020]
                     shadow-xl">

            <div class="grid md:grid-cols-2 gap-5">


                <!-- NAME -->

                <div>

                    <label class="block text-sm font-semibold mb-2">
                        Full Name
                    </label>

                    <input
                        type="text"
                        name="name"
                        required
                        placeholder="Enter your name"
                        class="w-full px-4 py-3.5 rounded-xl
                               bg-white dark:bg-[#151515]
                               border border-black/10
                               dark:border-white/10
                               outline-none
                               focus:border-[#C9A227]
                               transition">

                </div>


                <!-- PHONE -->

                <div>

                    <label class="block text-sm font-semibold mb-2">
                        Phone Number
                    </label>

                    <input
                        type="tel"
                        name="phone"
                        required
                        pattern="[0-9]{10}"
                        maxlength="10"
                        placeholder="10 digit mobile number"
                        class="w-full px-4 py-3.5 rounded-xl
                               bg-white dark:bg-[#151515]
                               border border-black/10
                               dark:border-white/10
                               outline-none
                               focus:border-[#C9A227]
                               transition">

                </div>


                <!-- EMAIL -->

                <div>

                    <label class="block text-sm font-semibold mb-2">
                        Email Address
                    </label>

                    <input
                        type="email"
                        name="email"
                        required
                        autocomplete="email"
                        placeholder="you@example.com"
                        class="w-full px-4 py-3.5 rounded-xl
                               bg-white dark:bg-[#151515]
                               border border-black/10
                               dark:border-white/10
                               outline-none
                               focus:border-[#C9A227]
                               transition">

                </div>


                <!-- SERVICE -->

                <div>

                    <label class="block text-sm font-semibold mb-2">
                        Looking for
                    </label>

                    <select
                        id="audienceSelect"
                        class="w-full px-4 py-3.5 rounded-xl
                               bg-white dark:bg-[#151515]
                               border border-black/10 dark:border-white/10
                               outline-none focus:border-[#C9A227]">
                        <option value="men">Men's services</option>
                        <option value="women">Women's services</option>
                    </select>

                </div>

                <div>

                    <label class="block text-sm font-semibold mb-2">
                        Service
                    </label>

                    <select
                        id="serviceSelect"
                        name="service"
                        required
                        class="w-full px-4 py-3.5 rounded-xl
                               bg-white dark:bg-[#151515]
                               border border-black/10
                               dark:border-white/10
                               outline-none
                               focus:border-[#C9A227]">

                        <option value="">
                            Select a service
                        </option>

                        {% for service in men_services %}

                        <option value="{{ service.name }}" data-price="{{ service.price }}" data-category="men">
                            {{ service.name }} — ₹{{ service.price }}
                        </option>

                        {% endfor %}

                        {% for service in women_services %}

                        <option value="{{ service.name }}" data-price="{{ service.price }}" data-category="women">
                            {{ service.name }} — ₹{{ service.price }}
                        </option>

                        {% endfor %}

                    </select>

                </div>


                <!-- PAYMENT -->

                <div>

                    <label class="block text-sm font-semibold mb-2">
                        Payment Option
                    </label>

                    <select
                        name="payment_option"
                        required
                        class="w-full px-4 py-3.5 rounded-xl
                               bg-white dark:bg-[#151515]
                               border border-black/10
                               dark:border-white/10
                               outline-none
                               focus:border-[#C9A227]">

                        <option value="">Choose payment option</option>

                        {% for payment_option in payment_options %}
                        <option value="{{ payment_option }}">
                            {{ payment_option }}
                        </option>
                        {% endfor %}

                    </select>

                </div>


                <!-- STYLIST -->

                <div>

                    <label class="block text-sm font-semibold mb-2">
                        Barber / Stylist
                    </label>

                    <select
                        name="stylist"
                        required
                        class="w-full px-4 py-3.5 rounded-xl
                               bg-white dark:bg-[#151515]
                               border border-black/10
                               dark:border-white/10
                               outline-none
                               focus:border-[#C9A227]">

                        <option value="">
                            Choose stylist
                        </option>

                        <option value="Arjun — Senior Barber" data-category="men">Arjun — Senior Barber</option>
                        <option value="Karan — Hair Specialist" data-category="men">Karan — Hair Specialist</option>
                        <option value="Riya — Senior Stylist" data-category="women">Riya — Senior Stylist</option>
                        <option value="Meera — Color Specialist" data-category="women">Meera — Color Specialist</option>

                    </select>

                </div>


                <!-- DATE -->

                <div>

                    <label class="block text-sm font-semibold mb-2">
                        Appointment Date
                    </label>

                    <input
                        type="date"
                        id="appointmentDate"
                        name="date"
                        required
                        aria-describedby="bookingWindowHint"
                        class="w-full px-4 py-3.5 rounded-xl
                               bg-white dark:bg-[#151515]
                               border border-black/10
                               dark:border-white/10
                               outline-none
                               focus:border-[#C9A227]">

                </div>


                <!-- TIME -->

                <div>

                    <label class="block text-sm font-semibold mb-2">
                        Appointment Time
                    </label>

                    <input type="hidden" name="time" required>

                    <button id="timePickerToggle"
                            type="button"
                            class="w-full px-4 py-3.5 rounded-xl text-left
                                   bg-white/70 dark:bg-[#151515]/70
                                   border border-black/10 dark:border-white/10
                                   font-semibold hover:border-[#C9A227] transition">
                        Choose a time
                    </button>

                    <div id="timeSlots"
                        class="slot-panel grid grid-cols-3 sm:grid-cols-4 gap-2 mt-3"
                        aria-label="Available appointment times">
                    </div>

                </div>

            </div>

            <p id="availabilityMessage"
               class="hidden mt-4 rounded-xl px-4 py-3 text-sm font-semibold"
               role="status"
               aria-live="polite"></p>

            <p id="bookingWindowHint" class="mt-3 text-xs opacity-50">
                Book today or a date within the next 7 days. Today’s past times are unavailable.
            </p>


            <button
                type="submit"
                class="shine w-full mt-7 py-4 rounded-xl
                       gold-gradient text-white
                       font-bold text-lg
                       shadow-xl hover:scale-[1.01]
                       transition">

                Confirm Appointment →

            </button>


            <p class="text-center text-xs opacity-40 mt-4">
                We will use your phone number only to confirm
                your appointment.
            </p>

        </form>

    </div>

</section>



<!-- =====================================================
     FOOTER
===================================================== -->

<footer class="bg-[#181818] text-white py-8">

    <div class="max-w-7xl mx-auto px-5 lg:px-8">

        <div class="grid md:grid-cols-3 gap-10">


            <div>

                <div class="display-font text-2xl font-bold">
                    VELORA
                </div>

                <p class="text-white/50 text-sm mt-3 max-w-xs">
                    Premium unisex hair studio created
                    for modern style and effortless confidence.
                </p>

            </div>


            <div>

                <div class="font-bold mb-4">
                    Studio Hours
                </div>

                <div class="text-sm text-white/50 space-y-2">

                    <div>
                        Monday — Sunday
                    </div>

                    <div>
                        10:00 AM — 9:00 PM
                    </div>

                </div>

            </div>


            <div>

                <div class="font-bold mb-4">
                    Contact
                </div>

                <div class="text-sm text-white/50 space-y-2">

                    <div>
                        📍 Your City, India
                    </div>

                    <div>
                        📞 +91 98765 43210
                    </div>

                    <div>
                        ✉️ hello@velora.in
                    </div>

                    <a href="https://www.google.com/maps/search/?api=1&query=Velora+Unisex+Hair+Studio+India"
                       target="_blank"
                       rel="noopener"
                       class="group block mt-4 rounded-2xl overflow-hidden border border-white/10">
                        <img src="https://images.unsplash.com/photo-1526778548025-fa2f459cd5c1?auto=format&fit=crop&w=700&q=80"
                             alt="Map showing the route to Velora"
                             class="w-full h-28 object-cover opacity-75 group-hover:opacity-100 transition">
                        <span class="block bg-white/10 px-3 py-2 text-xs text-white">Open Google Maps →</span>
                    </a>

                </div>

            </div>

        </div>


        <div class="border-t border-white/10 mt-10 pt-7
                    flex flex-col sm:flex-row
                    justify-between gap-3
                    text-xs text-white/30">

            <span>
                © 2026 Velora Hair Studio
            </span>

            <span>
                Personal style, thoughtfully made.
            </span>

        </div>

    </div>

</footer>



<!-- =====================================================
     JAVASCRIPT
===================================================== -->

<script>

    // -----------------------------------------------------
    // MOBILE MENU
    // -----------------------------------------------------

    function toggleMobileMenu() {

        const menu = document.getElementById("mobileMenu");

        menu.classList.toggle("active");

    }


    function closeMobileMenu() {

        document
            .getElementById("mobileMenu")
            .classList.remove("active");

    }


    // -----------------------------------------------------
    // SERVICE TABS
    // -----------------------------------------------------

    function showServices(type) {

        const men = document.getElementById("menServices");
        const women = document.getElementById("womenServices");

        const menTab = document.getElementById("menTab");
        const womenTab = document.getElementById("womenTab");


        if (type === "men") {

            men.classList.remove("hidden");
            women.classList.add("hidden");

            menTab.classList.add(
                "bg-[#181818]",
                "text-white",
                "dark:bg-white",
                "dark:text-black"
            );

            womenTab.classList.remove(
                "bg-[#181818]",
                "text-white",
                "dark:bg-white",
                "dark:text-black"
            );

        } else {

            women.classList.remove("hidden");
            men.classList.add("hidden");

            womenTab.classList.add(
                "bg-[#181818]",
                "text-white",
                "dark:bg-white",
                "dark:text-black"
            );

            menTab.classList.remove(
                "bg-[#181818]",
                "text-white",
                "dark:bg-white",
                "dark:text-black"
            );

        }

        const audienceSelect = document.getElementById("audienceSelect");
        if (audienceSelect) {
            audienceSelect.value = type;
            filterBookingOptions(type);
        }

    }


    function filterBookingOptions(type) {
        const serviceSelect = document.getElementById("serviceSelect");
        const stylistSelect = document.querySelector('select[name="stylist"]');
        if (!serviceSelect || !stylistSelect) return;

        [serviceSelect, stylistSelect].forEach(select => {
            Array.from(select.options).forEach(option => {
                if (option.dataset.category) {
                    option.hidden = option.dataset.category !== type;
                }
            });
            if (select.selectedOptions[0] && select.selectedOptions[0].hidden) {
                select.value = "";
            }
        });
    }


    // -----------------------------------------------------
    // SELECT SERVICE FROM CARD
    // -----------------------------------------------------

    function selectService(serviceName) {

        const select = document.getElementById("serviceSelect");

        select.value = serviceName;
        const selected = select.selectedOptions[0];
        if (selected && selected.dataset.category) {
            document.getElementById("audienceSelect").value = selected.dataset.category;
            filterBookingOptions(selected.dataset.category);
            select.value = serviceName;
        }
        document
            .getElementById("booking")
            .scrollIntoView({
                behavior: "smooth"
            });

    }


    // -----------------------------------------------------
    // Keep the browser controls aligned with the server booking window.
    // -----------------------------------------------------

    window.addEventListener("DOMContentLoaded", function() {

        const dateInput =
            document.getElementById("appointmentDate");

        if (dateInput) {

            const formatDate = date => {
                const year = date.getFullYear();
                const month = String(date.getMonth() + 1).padStart(2, "0");
                const day = String(date.getDate()).padStart(2, "0");
                return `${year}-${month}-${day}`;
            };
            const india = indiaNow();
            const today = `${india.year}-${india.month}-${india.day}`;
            const todayDate = new Date(`${today}T00:00:00`);
            const lastDate = new Date(todayDate);
            lastDate.setDate(lastDate.getDate() + 7);
            dateInput.min = today;
            dateInput.max = formatDate(lastDate);

            dateInput.addEventListener("change", () => {
                const now = indiaNow();
                const selectedToday = dateInput.value === `${now.year}-${now.month}-${now.day}`;
                timeInput.min = selectedToday
                    ? `${now.hour}:${now.minute}`
                    : "10:00";
            });

        }

        const timeInput = document.querySelector('input[name="time"]');
        const timePickerToggle = document.getElementById("timePickerToggle");
        const timeSlots = document.getElementById("timeSlots");
        const stylistInput = document.querySelector('select[name="stylist"]');
        const audienceSelect = document.getElementById("audienceSelect");
        const availabilityMessage = document.getElementById("availabilityMessage");
        let availabilityRequest;

        function indiaNow() {
            return new Intl.DateTimeFormat("en-CA", {
                timeZone: "Asia/Kolkata",
                year: "numeric", month: "2-digit", day: "2-digit",
                hour: "2-digit", minute: "2-digit", hour12: false
            }).formatToParts(new Date()).reduce((values, part) => {
                values[part.type] = part.value;
                return values;
            }, {});
        }

        function renderTimeSlots() {
            const slots = document.getElementById("timeSlots");
            if (!slots) return;
            for (let minutes = 600; minutes <= 1230; minutes += 15) {
                const value = `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
                const button = document.createElement("button");
                button.type = "button";
                button.textContent = value;
                button.className = "time-slot rounded-lg border border-green-500/30 bg-green-500 text-white py-2 text-sm font-semibold";
                button.addEventListener("click", () => {
                    timeInput.value = value;
                    timePickerToggle.textContent = `Selected time: ${value}`;
                    slots.querySelectorAll(".time-slot").forEach(item => item.classList.remove("selected"));
                    button.classList.add("selected");
                    slots.classList.remove("open");
                    timeInput.dispatchEvent(new Event("change", { bubbles: true }));
                });
                slots.appendChild(button);
            }
        }

        renderTimeSlots();
        timePickerToggle.addEventListener("click", () => {
            timeSlots.classList.toggle("open");
        });
        filterBookingOptions(audienceSelect.value);
        audienceSelect.addEventListener("change", () => filterBookingOptions(audienceSelect.value));

        function checkAvailability() {
            const date = dateInput.value;
            const time = timeInput.value;
            const stylist = stylistInput.value;

            if (!date || !time || !stylist) {
                availabilityMessage.classList.add("hidden");
                return;
            }

            if (availabilityRequest) {
                availabilityRequest.abort();
            }

            availabilityRequest = new AbortController();
            availabilityMessage.textContent = "Checking availability...";
            availabilityMessage.className =
                "mt-4 rounded-xl px-4 py-3 text-sm font-semibold bg-black/5 dark:bg-white/10";

            fetch(`/availability?date=${encodeURIComponent(date)}&time=${encodeURIComponent(time)}&stylist=${encodeURIComponent(stylist)}`, {
                signal: availabilityRequest.signal,
            })
                .then(response => response.json())
                .then(result => {
                    availabilityMessage.textContent = result.empty
                        ? "Sheet is empty. This is the first available booking."
                        : result.message;
                    availabilityMessage.className = result.available
                        ? "mt-4 rounded-xl px-4 py-3 text-sm font-semibold bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-200"
                        : "mt-4 rounded-xl px-4 py-3 text-sm font-semibold bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-200";
                })
                .catch(error => {
                    if (error.name !== "AbortError") {
                        availabilityMessage.textContent = "Availability could not be checked.";
                        availabilityMessage.className =
                            "mt-4 rounded-xl px-4 py-3 text-sm font-semibold bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-200";
                    }
                });
        }

        [dateInput, timeInput, stylistInput].forEach(input => {
            input.addEventListener("change", checkAvailability);
        });

        document.getElementById("bookingForm").addEventListener("submit", async event => {
            event.preventDefault();
            const form = event.currentTarget;
            const submitButton = form.querySelector('button[type="submit"]');
            submitButton.disabled = true;
            submitButton.textContent = "Confirming...";

            try {
                const response = await fetch(form.action, {
                    method: "POST",
                    body: new FormData(form),
                    headers: { "Accept": "application/json" }
                });
                const result = await response.json();
                availabilityMessage.textContent = result.message || "Unable to complete booking.";
                availabilityMessage.className = result.ok
                    ? "mt-4 rounded-xl px-4 py-3 text-sm font-semibold bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-200"
                    : "mt-4 rounded-xl px-4 py-3 text-sm font-semibold bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-200";
                availabilityMessage.classList.remove("hidden");
                if (result.ok) {
                    form.reset();
                    timePickerToggle.textContent = "Choose a time";
                    timeSlots.classList.remove("open");
                    timeSlots.querySelectorAll(".time-slot").forEach(item => item.classList.remove("selected"));
                }
            } catch (error) {
                availabilityMessage.textContent = "Booking could not be completed. Please try again.";
                availabilityMessage.className = "mt-4 rounded-xl px-4 py-3 text-sm font-semibold bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-200";
                availabilityMessage.classList.remove("hidden");
            } finally {
                submitButton.disabled = false;
                submitButton.textContent = "Confirm Appointment →";
            }
        });

    });


    // -----------------------------------------------------
    // AUTO HIDE FLASH MESSAGE
    // -----------------------------------------------------

    setTimeout(function() {

        const messages =
            document.querySelectorAll(
                ".fixed.top-24.right-5"
            );

        messages.forEach(function(message) {

            message.style.transition = "opacity .5s";
            message.style.opacity = "0";

            setTimeout(function() {
                message.remove();
            }, 500);

        });

    }, 4000);

</script>

</body>
</html>
"""


# =========================================================
# ADMIN HTML
# =========================================================

ADMIN_HTML = r"""
<!DOCTYPE html>
<html lang="en" class="scroll-smooth">

<head>

    <meta charset="UTF-8">

    <meta name="viewport"
          content="width=device-width, initial-scale=1.0">

    <title>Velora Admin</title>

    <script src="https://cdn.tailwindcss.com"></script>

    <script>
        tailwind.config = {
            darkMode: 'class'
        }
    </script>

    <link rel="preconnect"
          href="https://fonts.googleapis.com">

    <link rel="preconnect"
          href="https://fonts.gstatic.com"
          crossorigin>

    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Playfair+Display:wght@600;700&display=swap"
          rel="stylesheet">

    <style>

        body {
            font-family: 'Inter', sans-serif;
        }

        .display-font {
            font-family: 'Playfair Display', serif;
        }

        .gold-gradient {
            background: linear-gradient(
                135deg,
                #b88a18,
                #e6c65c,
                #a87d16
            );
        }

    </style>

</head>


<body class="bg-[#F8F5EF] text-[#181818] min-h-screen">


<!-- HEADER -->

<header class="border-b border-black/10 bg-white/75">

    <div class="max-w-7xl mx-auto px-5 py-5
                flex items-center justify-between">

        <div>

            <div class="display-font text-2xl font-bold">
                VELORA
            </div>

            <div class="text-xs opacity-50">
                ADMIN DASHBOARD
            </div>

        </div>


        <div class="flex items-center gap-3">

            <a href="{{ url_for('home') }}"
               class="px-5 py-2.5 rounded-full
                      gold-gradient text-white
                      font-semibold text-sm">

                ← Website

            </a>

        </div>

    </div>

</header>



<!-- CONTENT -->

<main class="max-w-7xl mx-auto px-5 py-12">


    <!-- TITLE -->

    <div class="flex flex-col md:flex-row
                justify-between gap-5
                md:items-center">

        <div>

            <p class="text-[#C9A227]
                      font-bold tracking-[.2em]
                      text-xs uppercase">

                Management

            </p>

            <h1 class="display-font text-4xl font-bold mt-2">
                Appointments
            </h1>

            <p class="opacity-50 mt-2">
                Manage all salon reservations.
            </p>

        </div>


        {% if appointments %}

        <form action="{{ url_for('clear_appointments') }}"
              method="POST"
              onsubmit="return confirm('Delete ALL appointments? This cannot be undone.');">

            <button
                type="submit"
                class="px-5 py-3 rounded-xl
                       bg-red-600 text-white
                       font-semibold
                       hover:bg-red-700 transition">

                🗑 Clear All

            </button>

        </form>

        {% endif %}

    </div>


    <!-- STATS -->

    <div class="grid sm:grid-cols-3 gap-4 mt-8">

        <div class="p-6 rounded-2xl
                    bg-white dark:bg-[#1c1c1c]
                    border border-black/10
                    dark:border-white/10">

            <div class="text-sm opacity-50">
                Total Appointments
            </div>

            <div class="text-3xl font-bold mt-2">
                {{ appointments|length }}
            </div>

        </div>


        <div class="p-6 rounded-2xl
                    bg-white dark:bg-[#1c1c1c]
                    border border-black/10
                    dark:border-white/10">

            <div class="text-sm opacity-50">
                Studio Hours
            </div>

            <div class="text-3xl font-bold mt-2">
                10 AM — 9 PM
            </div>

        </div>


        <div class="p-6 rounded-2xl
                    bg-white dark:bg-[#1c1c1c]
                    border border-black/10
                    dark:border-white/10">

            <div class="text-sm opacity-50">
                Database
            </div>

            <div class="text-lg font-bold mt-3
                        text-green-600">

                ● Connected

            </div>

        </div>

    </div>



    <!-- TABLE -->

    <div class="mt-8 rounded-3xl
                overflow-hidden
                border border-black/10
                dark:border-white/10
                bg-white dark:bg-[#1c1c1c]">

        {% if appointments %}

        <div class="overflow-x-auto">

            <table class="w-full text-left">

                <thead class="bg-black/[.03]
                              dark:bg-white/[.04]">

                    <tr>

                        <th class="px-5 py-4 text-xs
                                   uppercase tracking-wider
                                   opacity-50">
                            #
                        </th>

                        <th class="px-5 py-4 text-xs
                                   uppercase tracking-wider
                                   opacity-50">
                            Customer
                        </th>

                        <th class="px-5 py-4 text-xs
                                   uppercase tracking-wider
                                   opacity-50">
                            Phone
                        </th>

                        <th class="px-5 py-4 text-xs
                                   uppercase tracking-wider
                                   opacity-50">
                            Service
                        </th>

                        <th class="px-5 py-4 text-xs
                                   uppercase tracking-wider
                                   opacity-50">
                            Stylist
                        </th>

                        <th class="px-5 py-4 text-xs
                                   uppercase tracking-wider
                                   opacity-50">
                            Date
                        </th>

                        <th class="px-5 py-4 text-xs
                                   uppercase tracking-wider
                                   opacity-50">
                            Time
                        </th>

                    </tr>

                </thead>


                <tbody class="divide-y
                              divide-black/5
                              dark:divide-white/5">

                    {% for appointment in appointments %}

                    <tr class="hover:bg-black/[.02]
                               dark:hover:bg-white/[.02]
                               transition">

                        <td class="px-5 py-5
                                   font-semibold">
                            {{ appointment.id }}
                        </td>


                        <td class="px-5 py-5">

                            <div class="font-semibold">
                                {{ appointment.name }}
                            </div>

                            <div class="text-xs opacity-40 mt-1">
                                {{ appointment.created_at }}
                            </div>

                        </td>


                        <td class="px-5 py-5">
                            {{ appointment.phone }}
                        </td>


                        <td class="px-5 py-5">

                            <span class="px-3 py-1.5
                                         rounded-full
                                         bg-[#C9A227]/10
                                         text-[#9a7510]
                                         dark:text-[#e6c65c]
                                         text-sm font-semibold">

                                {{ appointment.service }}

                            </span>

                        </td>


                        <td class="px-5 py-5">
                            {{ appointment.stylist }}
                        </td>


                        <td class="px-5 py-5
                                   font-semibold">

                            {{ appointment.date }}

                        </td>


                        <td class="px-5 py-5
                                   font-semibold">

                            {{ appointment.time }}

                        </td>

                    </tr>

                    {% endfor %}

                </tbody>

            </table>

        </div>

        {% else %}

        <div class="py-20 text-center">

            <div class="text-5xl mb-5">
                📅
            </div>

            <h2 class="text-xl font-bold">
                No appointments yet
            </h2>

            <p class="opacity-50 mt-2">
                New bookings will appear here.
            </p>

        </div>

        {% endif %}

    </div>

</main>



<script>
</script>


</body>
</html>
"""


# =========================================================
# HOME ROUTE
# =========================================================

@app.route("/")
def home():

    status = get_salon_status()

    return render_template_string(
        INDEX_HTML,
        status=status,
        men_services=MEN_SERVICES,
        women_services=WOMEN_SERVICES,
        payment_options=PAYMENT_OPTIONS
    )


# =========================================================
# BOOK APPOINTMENT
# =========================================================
@app.route("/availability")
def availability():
    appointment_date = request.args.get("date", "").strip()
    appointment_time = request.args.get("time", "").strip()
    stylist = request.args.get("stylist", "").strip()

    if not all([appointment_date, appointment_time, stylist]):
        return {"available": False, "message": "Choose a date, time, and stylist."}, 400

    window_error = validate_appointment_window(appointment_date, appointment_time)
    if window_error:
        return {"available": False, "message": window_error}, 400

    try:
        result = call_google_script(
            "GET",
            query={
                "action": "availability",
                "date": appointment_date,
                "time": appointment_time,
                "stylist": stylist,
            },
        )
        return jsonify(result), (200 if result.get("ok", False) else 409)
    except RuntimeError as error:
        return jsonify({"ok": False, "available": False, "message": str(error)}), 503


@app.route("/book", methods=["POST"])
def book():
    try:
        payload = request.get_json(silent=True) or request.form
        name = payload.get("name", "").strip()
        phone = payload.get("phone", "").strip()
        email = payload.get("email", "").strip().lower()
        service = payload.get("service", "").strip()
        stylist = payload.get("stylist", "").strip()
        appointment_date = payload.get("date", "").strip()
        appointment_time = payload.get("time", "").strip()
        payment_option = payload.get("payment_option", "").strip()
        service_price = SERVICE_PRICES.get(service)

        # Validation
        if not all([
            name,
            phone,
            email,
            service,
            stylist,
            appointment_date,
            appointment_time,
            payment_option
        ]):
            return jsonify({"ok": False, "code": "VALIDATION", "message": "Please fill in all appointment details."}), 400

        if not phone.isdigit() or len(phone) != 10:
            return jsonify({"ok": False, "code": "VALIDATION", "message": "Please enter a valid 10-digit phone number."}), 400

        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            return jsonify({"ok": False, "code": "VALIDATION", "message": "Please enter a valid email address."}), 400

        if service_price is None:
            return jsonify({"ok": False, "code": "VALIDATION", "message": "Please select a valid service."}), 400

        if payment_option not in PAYMENT_OPTIONS:
            return jsonify({"ok": False, "code": "VALIDATION", "message": "Please select a valid payment option."}), 400

        window_error = validate_appointment_window(
            appointment_date,
            appointment_time,
        )
        if window_error:
            return jsonify({"ok": False, "code": "VALIDATION", "message": window_error}), 400

        result = call_google_script("POST", {
            "name": name,
            "phone": phone,
            "email": email,
            "service": service,
            "stylist": stylist,
            "servicePrice": service_price,
            "date": appointment_date,
            "time": appointment_time,
            "paymentOption": payment_option,
        })
        status = 200 if result.get("ok") else (409 if result.get("code") == "DUPLICATE" else 400)
        return jsonify(result), status

    except RuntimeError as error:
        return jsonify({"ok": False, "code": "SERVICE_ERROR", "message": str(error)}), 503
# =========================================================
# ADMIN
# =========================================================

@app.route("/admin")
def admin():
    result = call_google_script("GET", query={"action": "list"})
    rows = result.get("bookings", [])
    appointments = [
        {
            "id": index,
            "name": row.get("Name", ""),
            "phone": row.get("Phone", ""),
            "email": row.get("Email", ""),
            "service": row.get("Service", ""),
            "stylist": row.get("Stylist", ""),
            "date": row.get("Appointment Date", ""),
            "time": row.get("Appointment Time", ""),
            "created_at": row.get("Booked At", ""),
        }
        for index, row in enumerate(rows, start=1)
    ]
    appointments.sort(key=lambda item: (item["date"], item["time"], -item["id"]))

    return render_template_string(
        ADMIN_HTML,
        appointments=appointments
    )


# =========================================================
# CLEAR APPOINTMENTS
# =========================================================

@app.route("/admin/clear", methods=["POST"])
def clear_appointments():
    result = call_google_script("POST", {"action": "clear"})
    if not result.get("ok"):
        flash(result.get("message", "Unable to clear appointments."), "error")
        return redirect(url_for("admin"))

    flash(
        "All appointments have been cleared.",
        "success"
    )

    return redirect(url_for("admin"))


# =========================================================
# START APPLICATION
# =========================================================
if __name__ == "__main__":

    print("=" * 55)
    print("VELORA UNISEX HAIR STUDIO")
    print("=" * 55)
    print("Website : http://127.0.0.1:5000")
    print("Admin   : http://127.0.0.1:5000/admin")
    print("Storage : Google Sheets")
    print("Booking : Google Apps Script /exec")
    print("=" * 55)

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )