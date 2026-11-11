APPLICATION = imu_test

BOARD ?= seeedstudio-xiao-nrf52840-sense

RIOTBASE ?= $(HOME)/riotproject

# Link layer / RPL networking (mirrored from
# examples/networking/gnrc/networking, the proven-working config)
USEMODULE += netdev_default
USEMODULE += auto_init_gnrc_netif
USEMODULE += gnrc_icmpv6_error
USEMODULE += gnrc_icmpv6_echo
USEMODULE += gnrc_ipv6_router_default
USEMODULE += gnrc_rpl
USEMODULE += auto_init_gnrc_rpl
USEMODULE += gnrc_sock_udp

# Sensor
USEMODULE += lsm6dsxx
USEMODULE += ztimer
USEMODULE += ztimer_msec

DEVELHELP ?= 1

include $(RIOTBASE)/Makefile.include
include $(RIOTMAKE)/default-radio-settings.inc.mk
