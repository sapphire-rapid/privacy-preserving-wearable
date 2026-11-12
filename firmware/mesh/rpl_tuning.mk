# Shared RPL / radio tuning for every device in the mesh (nodes AND border router).
# Included by mesh_node/Makefile and mesh_br/Makefile so all builds agree.
#
# Why every build and not just the BR: RIOT only puts the DODAG Configuration
# option (which carries these values) into some DIOs, so a node can join from a
# DIO without it and fall back to its OWN compile-time defaults.

# --- Radio: nRF52840 max TX power (RIOT default is 0 dBm) ---
CFLAGS += -DCONFIG_IEEE802154_DEFAULT_TXPOWER=8

# --- Trickle (DIO timer) -------------------------------------------------------
# Imin = 2^DIO_INTERVAL_MIN ms, Imax = Imin * 2^DOUBLINGS
#   RIOT default : 2^3  ms = 8 ms,   x 2^20 -> ~2.3 h max silence
#   Contiki-NG   : 2^12 ms = 4.1 s,  x 2^8  -> ~17.5 min
#   Thread (MLE) : 1 s .. 32 s
#   ours         : 2^10 ms = 1.02 s, x 2^5  -> ~33 s   (Thread-like)
CFLAGS += -DCONFIG_GNRC_RPL_DEFAULT_DIO_INTERVAL_MIN=10
CFLAGS += -DCONFIG_GNRC_RPL_DEFAULT_DIO_INTERVAL_DOUBLINGS=5

# --- Route / parent lifetime ----------------------------------------------------
# Route lifetime = DEFAULT_LIFETIME * LIFETIME_UNIT seconds (RIOT default 5*60 = 300 s).
# A parent that stops sending DIOs is probed after (LIFETIME-1)*UNIT s.
#   ours: 6 * 15 s = 90 s routes, probe a silent parent after 75 s.
# Must stay above RIOT's DAO refresh period (CONFIG_GNRC_RPL_DAO_DELAY_LONG, 60 s)
# and above Imax (~33 s), otherwise healthy routes/parents expire.
CFLAGS += -DCONFIG_GNRC_RPL_DEFAULT_LIFETIME=6
CFLAGS += -DCONFIG_GNRC_RPL_LIFETIME_UNIT=15
