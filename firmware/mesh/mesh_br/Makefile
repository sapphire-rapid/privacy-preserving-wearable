# mesh_br - RPL root / 6LoWPAN border router on the nRF52840 dongle.
# Trimmed copy of RIOT's examples/networking/gnrc/border_router, fixed to
# UPLINK=cdc-ecm + PREFIX_CONF=static, plus the boot-time fixes in main.c.
APPLICATION = mesh_br

BOARD ?= nrf52840dongle
RIOTBASE ?= $(HOME)/riotproject

# Addressing (unchanged from the working setup)
IPV6_ADDR   ?= 2001:db8:1::1         # BR uplink (cdc-ecm, towards Pi4 usb0)
UPLINK_PFX  ?= 2001:db8:1::/64       # uplink on-link prefix (the 'nib prefix add' fix)
IPV6_PREFIX ?= 2001:db8::/64         # wireless mesh prefix, also the DODAG prefix

include $(CURDIR)/../rpl_tuning.mk

USEMODULE += netdev_default
USEMODULE += auto_init_gnrc_netif
USEMODULE += gnrc_sixlowpan_border_router_default
USEMODULE += gnrc_icmpv6_echo
USEMODULE += gnrc_rpl
USEMODULE += gnrc_ipv6_static_addr
USEMODULE += random
USEMODULE += ztimer_msec

# cdc-ecm uplink to the Pi4 (stdio stays on the CDC-ACM serial)
USEMODULE += auto_init_usbus
USEMODULE += usbus_cdc_ecm

# shell kept for debugging: rpl, nib, ifconfig, ping
USEMODULE += shell
USEMODULE += shell_cmds_default
USEMODULE += ps

CFLAGS += -DCONFIG_GNRC_IPV6_STATIC_ADDR=\"$(strip $(IPV6_ADDR))\"
CFLAGS += -DCONFIG_GNRC_IPV6_STATIC_PREFIX=\"$(strip $(IPV6_PREFIX))\"
CFLAGS += -DMESH_UPLINK_PFX=\"$(strip $(UPLINK_PFX))\"

DEVELHELP ?= 1
QUIET ?= 1
SHOULD_RUN_KCONFIG ?=

include $(RIOTBASE)/Makefile.include
include $(RIOTMAKE)/default-radio-settings.inc.mk
