/* pipeline.c - see pipeline.h */
#include <string.h>

#include "pipeline.h"

void fall_pipe_reset(fall_pipe_t *p)
{
    p->n = 0;
    p->n_pend = 0;
    memset(p->xyz, 0, sizeof(p->xyz));
    memset(p->mag, 0, sizeof(p->mag));
}

void fall_pipe_push(fall_pipe_t *p, float x, float y, float z, fall_ev_t *ev)
{
    memset(ev, 0, sizeof(*ev));

    /* ---- ring buffers ---------------------------------------------------- */
    unsigned iw = p->n % WIN_SAMPLES;
    p->xyz[iw][0] = x;
    p->xyz[iw][1] = y;
    p->xyz[iw][2] = z;
    p->mag[p->n % CONFIRM_SAMPLES] = sqrtf(x * x + y * y + z * z);
    p->n++;
    uint32_t n = p->n;

    /* ---- confirm segments that complete on this sample ------------------- */
    /* pending ends are distinct, so at most one completes per push */
    for (unsigned k = 0; k < p->n_pend; k++) {
        if (p->pend_end[k] + CONFIRM_SAMPLES != n) {
            continue;
        }
        unsigned start = n % CONFIRM_SAMPLES;       /* oldest sample in ring */
        for (unsigned i = 0; i < CONFIRM_SAMPLES; i++) {
            p->seg[i] = p->mag[(start + i) % CONFIRM_SAMPLES];
        }
        float mean = 0.0f;
        for (unsigned i = 0; i < CONFIRM_SAMPLES; i++) {
            mean += p->seg[i];
        }
        mean /= (float)CONFIRM_SAMPLES;
        ev->conf_std = fall_std_pop(p->seg, CONFIRM_SAMPLES);
        ev->conf_mean = mean;
        ev->conf_trig_n = p->pend_end[k];
        ev->conf = fall_is_still(p->seg, CONFIRM_SAMPLES) ? FALL_CONF_CONFIRMED
                                                          : FALL_CONF_CANCELLED;
        if (ev->conf == FALL_CONF_CONFIRMED) {
            p->n_pend = 0;                  /* same fall: drop the others    */
        }
        else {
            for (unsigned j = k + 1; j < p->n_pend; j++) {
                p->pend_end[j - 1] = p->pend_end[j];
            }
            p->n_pend--;
        }
        break;
    }

    /* ---- stride window --------------------------------------------------- */
    if (n >= WIN_SAMPLES && ((n - WIN_SAMPLES) % STRIDE_SAMPLES) == 0) {
        unsigned start = n % WIN_SAMPLES;           /* oldest sample in ring */
        for (unsigned i = 0; i < WIN_SAMPLES; i++) {
            const float *s = p->xyz[(start + i) % WIN_SAMPLES];
            p->win[i][0] = s[0];
            p->win[i][1] = s[1];
            p->win[i][2] = s[2];
        }
        ev->window = 1;
        ev->wi = (n - WIN_SAMPLES) / STRIDE_SAMPLES;
        fall_features(p->win, WIN_SAMPLES, ev->feat);
        ev->prob = fall_lr_prob(ev->feat);
        ev->trigger = fall_trigger(ev->prob);
        if (ev->trigger) {
            if (p->n_pend < FALL_MAX_PEND) {
                p->pend_end[p->n_pend++] = n;
            }
            else {
                ev->pend_overflow = 1;
            }
        }
    }
}
