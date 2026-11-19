/*
 * host_pipe_test - runs the SAME pipeline.c + replay_seq.h as the board, with no
 * pacing, and prints the replay table.  Lets the on-board 'r' result be
 * predicted (and the logic debugged) before flashing.
 *
 *   gcc -O0 -Wall -I../include -I.. -o host_pipe_test host_pipe_test.c ../pipeline.c -lm
 */
#include <stdio.h>
#include <string.h>

#include "replay_seq.h"

int main(void)
{
    static fall_pipe_t pipe;
    int all = 1;

    printf("%-3s %-12s %-3s %-4s %-5s %-5s %-5s %-5s %-8s %-10s %-10s %s\n",
           "idx", "sequence", "src", "n", "wins", "trig", "conf", "canc",
           "pending", "w0_prob", "expect", "result");
    for (int idx = 0; idx < REPLAY_N_SEQ; idx++) {
        int kind, src;
        replay_seq_desc(idx, &kind, &src);
        int len = replay_seq_len(kind);
        replay_res_t res;
        memset(&res, 0, sizeof(res));
        fall_pipe_reset(&pipe);
        for (int k = 0; k < len; k++) {
            float s[3];
            fall_ev_t ev;
            replay_seq_sample(kind, src, k, s);
            fall_pipe_push(&pipe, s[0], s[1], s[2], &ev);
            replay_account(&res, &ev);
            if (ev.window || ev.conf) {
                printf("    ev idx=%d n=%d%s%s p=%.6f%s%s\n", idx, k + 1,
                       ev.window ? " win" : "", ev.trigger ? " TRIGGER" : "",
                       (double)ev.prob,
                       ev.conf == FALL_CONF_CONFIRMED ? " CONFIRMED" :
                       ev.conf == FALL_CONF_CANCELLED ? " CANCELLED" : "",
                       ev.conf ? "" : "");
            }
        }
        int pass = replay_pass(kind, &res);
        all &= pass;
        printf("%-3d %-12s %-3d %-4d %-5d %-5d %-5d %-5d %-8d %-10.6f %-10s %s\n",
               idx, replay_kind_name[kind], src, len, res.windows, res.n_trig,
               res.n_conf, res.n_canc, pipe.n_pend, (double)res.w0_prob,
               replay_expect(kind), pass ? "PASS" : "FAIL");
    }
    printf("\nRESULT: %s\n", all ? "ALL PASS" : "SOME FAILURES");
    return all ? 0 : 1;
}
