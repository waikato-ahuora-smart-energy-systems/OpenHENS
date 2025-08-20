from math import isclose

def check_temperatures(case, rel_tol=1e-3, abs_tol=1e-2, q_tol=1e-2) -> bool:
    issues = False
    for i in range(case.I):
        for j in range(case.J):
            for k in range(case.S):
                if case.Q_r[i][j][k][0] <= q_tol:
                    continue

                if case.non_isothermal_model:
                    # Inlet temperature check
                    T_h_in = case.T_h[i][k][0]
                    T_c_out_y = case.T_c_out_y[j][i][k][0]
                    theta1 = case.theta_1[i][j][k][0]

                    if not isclose(T_h_in, T_c_out_y + theta1, rel_tol=rel_tol, abs_tol=abs_tol) or T_h_in < T_c_out_y:
                        print(f'[Temp Error] H{i} C{j} S{k} T_h_in {T_h_in:.2f} < T_c_out_y {T_c_out_y:.2f} with theta1 {theta1:.2f} with Q_r {case.Q_r[i][j][k][0]:.2f} with z {case.z[i][j][k][0]}')
                        issues = True

                    # Outlet temperature check
                    T_h_out = case.T_h_out_x[i][j][k][0]
                    T_c_in = case.T_c[j][k+1][0]
                    theta2 = case.theta_2[i][j][k][0]

                    if not isclose(T_h_out, T_c_in + theta2, rel_tol=rel_tol, abs_tol=abs_tol) or T_h_out < T_c_in:
                        print(f'[Temp Error] H{i} C{j} S{k} T_h_out_x {T_h_out:.2f} < T_c_in {T_c_in:.2f} with theta2 {theta2:.2f} with Q_r {case.Q_r[i][j][k][0]:.2f} with z {case.z[i][j][k][0]}')
                        issues = True

                else:
                    # Inlet temperature check
                    T_h_in = case.T_h[i][k][0]
                    T_c_out = case.T_c[j][k][0]
                    theta1 = case.theta_1[i][j][k][0]

                    if T_h_in < T_c_out:
                        print(f'[Temp Error] H{i} C{j} S{k} T_h_in {T_h_in:.2f} < T_c_out {T_c_out:.2f} with theta1 {theta1:.2f} with Q_r {case.Q_r[i][j][k][0]:.2f} with z {case.z[i][j][k][0]}')
                        issues = True

                    # Outlet temperature check
                    T_h_out = case.T_h[i][k+1][0]
                    T_c_in = case.T_c[j][k+1][0]
                    theta2 = case.theta_2[i][j][k][0]

                    if T_h_out < T_c_in:
                        print(f'[Temp Error] H{i} C{j} S{k} T_h_out {T_h_out:.2f} < T_c_in {T_c_in:.2f} with theta2 {theta2:.2f} with Q_r {case.Q_r[i][j][k][0]:.2f} with z {case.z[i][j][k][0]}')
                        issues = True

    return not issues


def check_utility_costs(case, rel_tol=0.1, abs_tol=1) -> bool:
    issues = False

    post_HU = case.hu_cost[0] * sum(case.Q_h[j][0] for j in range(case.J))
    post_CU = case.cu_cost[0] * sum(case.Q_c[i][0] for i in range(case.I))

    model_HU = case.hu_cost_total.value[0]
    model_CU = case.cu_cost_total.value[0]

    # Check HU cost
    if not isclose(post_HU, model_HU, rel_tol=rel_tol, abs_tol=abs_tol):
        print(f'[Cost Mismatch] HU post {post_HU:.6f} != model {model_HU:.6f}')
        issues = True

    # Check CU cost
    if not isclose(post_CU, model_CU, rel_tol=rel_tol, abs_tol=abs_tol):
        print(f'[Cost Mismatch] CU post {post_CU:.6f} != model {model_CU:.6f}')
        issues = True

    return not issues


def check_area_costs(case, rel_tol=0.1, abs_tol=1, q_tol=1e-2) -> bool:

    issues = False
    for k in range(case.S):
        for j in range(case.J):
            allowed_hots = [i for i in range(case.I) if case.z_allowed[i][j][k] > 0]

            if not allowed_hots:
                continue

            # Total duty for this exchanger: skip check if it's negligible since there may be residual area 
            total_duty = sum(case.Q_r[i][j][k][0] for i in allowed_hots)
            if abs(total_duty) <= q_tol:
                continue

            # Compute area using Chen approximation
            post_area_chen = sum([
                (
                    case.Q_r[n][j][k][0] /
                    (case.U_r[n][j] *
                     ((case.theta_1[n][j][k][0] * case.theta_2[n][j][k][0] *
                       (case.theta_1[n][j][k][0] + case.theta_2[n][j][k][0]) / 2 + 1e-3) ** (1/3)))
                ) ** case.A_exp[0]
                for n in allowed_hots
            ]) * case.A_coeff[0]
            
            post_area_log = sum([
                (case.area_r[n][j][k]
                ) ** case.A_exp[0]
                for n in allowed_hots
            ]) * case.A_coeff[0]


            # Extract model area
            model_area = case.recovery_area_cost_filtered[k][j]
            if not isinstance(model_area, (int, float)):
                model_area = model_area.value[0]

            if not isclose(post_area_chen, model_area, rel_tol=rel_tol, abs_tol=abs_tol):
                print(f'[Area Error] S{k} C{j} post chen {post_area_chen:.4f} != model {model_area:.4f}')
                issues = True
            
            if not isclose(post_area_chen, model_area, rel_tol=rel_tol, abs_tol=abs_tol):
                print(f'[Area Error] S{k} C{j} post LMTD {post_area_log:.4f} != model {model_area:.4f}')
                issues = True    
                
    return not issues


def verify_solution(case) -> tuple[bool, list[str]]:
    failures = []

    if not check_temperatures(case):
        failures.append("temperature")

    if case.minimisation_goal == 'total cost' or case.minimisation_goal == 'variable total cost':
        if not check_utility_costs(case):
            failures.append("cost")


    if case.minimisation_goal == 'total cost' or case.minimisation_goal == 'variable total cost':
        if not check_area_costs(case):
            failures.append("area")

    return (len(failures) == 0), failures  