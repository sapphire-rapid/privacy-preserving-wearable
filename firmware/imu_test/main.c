/*
 * imu_test - LSM6DSXX accel/gyro read + UDP send over RPL mesh
 * Destination address is read live from RPL's own DODAG state
 * (gnrc_rpl_instances[].dodag.dodag_id) - no hardcoded IPv6 literal.
 */
#include <stdio.h>
#include <string.h>

#include "ztimer.h"
#include "lsm6dsxx.h"
#include "lsm6dsxx_params.h"

#include "net/sock/udp.h"
#include "net/gnrc/rpl.h"
#include "net/gnrc/rpl/dodag.h"
#include "net/ipv6/addr.h"

#define SLEEP_MSEC   (1000UL)
#define DEST_PORT    (8888U)

typedef struct __attribute__((packed)) {
    uint32_t seq;
    int16_t acc_x, acc_y, acc_z;
    int16_t gyro_x, gyro_y, gyro_z;
} imu_packet_t;

static bool _get_rpl_root_addr(ipv6_addr_t *out)
{
    for (unsigned i = 0; i < GNRC_RPL_INSTANCES_NUMOF; i++) {
        if (gnrc_rpl_instances[i].state != 0) {
            memcpy(out, &gnrc_rpl_instances[i].dodag.dodag_id, sizeof(ipv6_addr_t));
            return true;
        }
    }
    return false;
}

int main(void)
{
    lsm6dsxx_t dev;
    lsm6dsxx_3d_data_t acc_value;
    lsm6dsxx_3d_data_t gyro_value;
    uint32_t seq = 0;

    puts("imu_test: initializing LSM6DSXX...");
    if (lsm6dsxx_init(&dev, lsm6dsxx_params) != LSM6DSXX_OK) {
        puts("[ERROR] IMU init failed");
        return 1;
    }
    puts("[OK] IMU ready\n");

    while (1) {
        ipv6_addr_t root_addr;

        if (!_get_rpl_root_addr(&root_addr)) {
            puts("[WAIT] not joined to a DODAG yet");
            ztimer_sleep(ZTIMER_MSEC, SLEEP_MSEC);
            continue;
        }

        if (lsm6dsxx_read_acc(&dev, &acc_value) != LSM6DSXX_OK ||
            lsm6dsxx_read_gyro(&dev, &gyro_value) != LSM6DSXX_OK) {
            puts("[ERROR] IMU read failed");
            ztimer_sleep(ZTIMER_MSEC, SLEEP_MSEC);
            continue;
        }

        imu_packet_t packet = {
            .seq = seq,
            .acc_x = acc_value.x, .acc_y = acc_value.y, .acc_z = acc_value.z,
            .gyro_x = gyro_value.x, .gyro_y = gyro_value.y, .gyro_z = gyro_value.z,
        };

        sock_udp_ep_t remote = {
            .family = AF_INET6,
            .netif = SOCK_ADDR_ANY_NETIF,
            .port = DEST_PORT,
        };
        memcpy(remote.addr.ipv6, &root_addr, sizeof(root_addr));

        char addr_str[IPV6_ADDR_MAX_STR_LEN];
        ipv6_addr_to_str(addr_str, &root_addr, sizeof(addr_str));

        ssize_t res = sock_udp_send(NULL, &packet, sizeof(packet), &remote);
        if (res < 0) {
            printf("[FAIL] seq=%lu -> %s (err %d)\n",
                   (unsigned long)seq, addr_str, (int)res);
        }
        else {
            printf("[SENT] seq=%lu -> %s (%d bytes)\n",
                   (unsigned long)seq, addr_str, (int)res);
        }

        seq++;
        ztimer_sleep(ZTIMER_MSEC, SLEEP_MSEC);
    }

    return 0;
}
