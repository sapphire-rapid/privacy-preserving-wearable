APPLICATION = max30102_probe

BOARD ?= seeedstudio-xiao-nrf52840-sense
RIOTBASE ?= $(CURDIR)/../../riotproject
CFLAGS += -DCONFIG_IEEE802154_DEFAULT_TXPOWER=8

USEMODULE += netdev_default
USEMODULE += auto_init_gnrc_netif
USEMODULE += gnrc_icmpv6_error
USEMODULE += gnrc_icmpv6_echo
USEMODULE += gnrc_ipv6_router_default
USEMODULE += gnrc_rpl
USEMODULE += auto_init_gnrc_rpl
USEMODULE += gnrc_sock_udp

USEMODULE += periph_i2c
USEMODULE += ztimer
USEMODULE += ztimer_msec

DEVELHELP ?= 1

include $(RIOTBASE)/Makefile.include
include $(RIOTMAKE)/default-radio-settings.inc.mk
