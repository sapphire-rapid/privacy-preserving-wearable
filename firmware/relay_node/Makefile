APPLICATION = relay_node

BOARD ?= seeedstudio-xiao-nrf52840-sense

RIOTBASE ?= $(HOME)/riotproject

# Match HR XIAO radio power (+8 dBm). Without this the relay runs at the
# 0 dBm default, which weakens BOTH hops the relay transmits on.
CFLAGS += -DCONFIG_IEEE802154_DEFAULT_TXPOWER=8

# Link layer / RPL networking (mirrored from imu_test, the proven-working config)
USEMODULE += netdev_default
USEMODULE += auto_init_gnrc_netif
USEMODULE += gnrc_icmpv6_error
USEMODULE += gnrc_icmpv6_echo
USEMODULE += gnrc_ipv6_router_default
USEMODULE += gnrc_rpl
USEMODULE += auto_init_gnrc_rpl
USEMODULE += gnrc_sock_udp

USEMODULE += ztimer
USEMODULE += ztimer_msec

DEVELHELP ?= 1

include $(RIOTBASE)/Makefile.include
include $(RIOTMAKE)/default-radio-settings.inc.mk
