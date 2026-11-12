#ifndef FALL_TREE_H
#define FALL_TREE_H

#define N_FEATURES 8

/* Feature order:
 * 0: max_mag
 * 1: min_mag
 * 2: mean_mag
 * 3: std_mag
 * 4: range_mag
 * 5: max_jerk
 * 6: std_mag_post
 * 7: count_low
 */

static inline int fall_predict(const float f[N_FEATURES]) {
    if (f[0] <= 2.543266f) {  /* max_mag */
        if (f[0] <= 2.019027f) {  /* max_mag */
            if (f[4] <= 1.038938f) {  /* range_mag */
                return 0;
            } else {
                if (f[6] <= 0.187436f) {  /* std_mag_post */
                    if (f[3] <= 0.181528f) {  /* std_mag */
                        return 0;
                    } else {
                        return 0;
                    }
                } else {
                    if (f[1] <= 0.710176f) {  /* min_mag */
                        return 0;
                    } else {
                        return 0;
                    }
                }
            }
        } else {
            if (f[6] <= 0.276843f) {  /* std_mag_post */
                if (f[3] <= 0.225558f) {  /* std_mag */
                    if (f[0] <= 2.052462f) {  /* max_mag */
                        return 0;
                    } else {
                        return 0;
                    }
                } else {
                    if (f[6] <= 0.043176f) {  /* std_mag_post */
                        return 0;
                    } else {
                        return 1;
                    }
                }
            } else {
                if (f[6] <= 0.289095f) {  /* std_mag_post */
                    if (f[6] <= 0.289056f) {  /* std_mag_post */
                        return 0;
                    } else {
                        return 1;
                    }
                } else {
                    if (f[2] <= 0.910147f) {  /* mean_mag */
                        return 0;
                    } else {
                        return 0;
                    }
                }
            }
        }
    } else {
        if (f[6] <= 0.578293f) {  /* std_mag_post */
            if (f[6] <= 0.021560f) {  /* std_mag_post */
                return 0;
            } else {
                if (f[6] <= 0.411077f) {  /* std_mag_post */
                    if (f[3] <= 0.280573f) {  /* std_mag */
                        return 0;
                    } else {
                        return 1;
                    }
                } else {
                    if (f[0] <= 3.717488f) {  /* max_mag */
                        return 0;
                    } else {
                        return 1;
                    }
                }
            }
        } else {
            if (f[0] <= 4.484429f) {  /* max_mag */
                if (f[7] <= 8.500000f) {  /* count_low */
                    if (f[4] <= 3.595229f) {  /* range_mag */
                        return 0;
                    } else {
                        return 1;
                    }
                } else {
                    if (f[4] <= 4.271953f) {  /* range_mag */
                        return 0;
                    } else {
                        return 0;
                    }
                }
            } else {
                if (f[6] <= 0.988473f) {  /* std_mag_post */
                    if (f[0] <= 4.981148f) {  /* max_mag */
                        return 1;
                    } else {
                        return 1;
                    }
                } else {
                    if (f[4] <= 4.106893f) {  /* range_mag */
                        return 0;
                    } else {
                        return 0;
                    }
                }
            }
        }
    }
}

#endif
