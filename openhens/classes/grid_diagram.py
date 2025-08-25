'''
__author__ = 'Keegan Hall'
__credits__ = ['']

Class for drawing HEN grid diagrams with the option to show process source, air source and air sink HP's
'''

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import sys
from pathlib import Path

parent_folder = Path(__file__).parent # location of folder that contains the entire package

class Grid_Diagram():
        def __init__(self, network, non_iso, draw_stages=False, draw_HP=False, comparison_network=None):
            """Class constructor"""
            self.network = network
            self.draw_HP = draw_HP # NOTE: Synthesising heat pumps is within SynHEAT is in devolopment and will be released as a future update
                        
            # Manually defined spacing values
            self.stream_spacing = 2 # y-axis gap between streams should be scaled based upon problem size
            self.y_start = 2 # y-axis co-ord for stream start
            self.x_start = 0 # x-axis co-ord for stream start
            self.utility_length = 3.5*self.network.S/2
            self.tol = 1 # kW, tolerance for showing HX since some units are very small and are just a result of solver convergence
            self.size_of_font = 18 # size of font for stream labels
            self.duty_font_size = 14 # size of font for duty labels
            self.temp_font_size = 14 # size of font for temperature labels
            
            self.branch_spacing = 2 # y-axis gap between branches
            self.x_text_offset = 0.75 # x axis distance between stream end and stream label
            self.draw_stages = draw_stages # user input for whether stages should be shown
            
            # Extract highlighted matches
            self.common_matches = [] # list of highlighted matches common between network & to be drawn on grid diagram, if not provided then no highlights will be drawn
            self.exlusive_matches = [] # list of highlighted matches exlusive to the comparison network  network & to be drawn on grid diagram, if not provided then no highlights will be drawn
            if comparison_network is not None:
                self._extract_common_matches(comparison_network)
                self._extract_exclusive_matches(comparison_network)

            # Label parameters
            self.figure_size = (12.69, 8.27)  # A4 landscape size in inches for 2 figures (width, height)
            self.fig, self.ax = plt.subplots(figsize=self.figure_size)
            
            # Lists
            self.hot_y_coords = [] # list of y-coordinates for each hot stream (hot n to 0) [H2,H1,H0]
            self.cold_y_coords = [] # list of y-coordinates for each cold stream (cold n to 0)
            self.stage_bounaries = [] # list of x-coordinates for stage boundaries
            
            # Run functions
            self._process_match_existance()
            self._calculate_spacing()
            self.draw_streams()
            self.draw_branches()
            self.draw_recovery_matches()
            self.draw_utility_match()
            
            ## As optional functions
            self.add_duties()
            self.add_temps(non_iso)
    
            self.plot_setup()

        def _extract_common_matches(self, comparison_network):
            """Extracts common matches from the network and comparison network"""
            self.common_matches = []

            # Recovery matches
            for i in range(comparison_network.I):
                for j in range(comparison_network.J):
                    for k in range(comparison_network.S):
                        if self.network.Q_r[i][j][k][0] > self.tol and comparison_network.Q_r[i][j][k][0] > self.tol:
                            self.common_matches.append(('recovery', i, j, k))

            # Hot utility matches 
            for j in range(comparison_network.J):
                if self.network.Q_h[j][0] > self.tol and comparison_network.Q_h[j][0] > self.tol:
                    self.common_matches.append(('HU', j))

            # Cold utility matches 
            for i in range(comparison_network.I):
                if self.network.Q_c[i][0] > self.tol and comparison_network.Q_c[i][0] > self.tol:
                    self.common_matches.append(('CU', i))
                    
        def _extract_exclusive_matches(self, comparison_network):
            """Extracts exlusive matches only to the comparison network"""
            # Recovery matches
            for i in range(comparison_network.I):
                for j in range(comparison_network.J):
                    for k in range(comparison_network.S):
                        if self.network.Q_r[i][j][k][0] < self.tol and comparison_network.Q_r[i][j][k][0] > self.tol:
                            self.exlusive_matches.append(('recovery', i, j, k))
                            
            # Hot utility matches 
            for j in range(comparison_network.J):
                if self.network.Q_h[j][0] < self.tol and comparison_network.Q_h[j][0] > self.tol:
                    self.exlusive_matches.append(('HU', j))

            # Cold utility matches 
            for i in range(comparison_network.I):
                if self.network.Q_c[i][0] < self.tol and comparison_network.Q_c[i][0] > self.tol:
                    self.exlusive_matches.append(('CU', i))


        def _process_match_existance(self):
            """Identify existence of each match"""
            # Determine whether there is a HP or process match in that position
            if self.draw_HP == True: # check for HP's
                self.recovery_match = [[[1 if (self.network.z[i][j][k][0] > 0 and self.network.Q_r[i][j][k][0] > self.tol) else 0 for k in range(self.network.S)] for j in range(self.network.J)] for i in range(self.network.I)]
                self.processHP_match = [[[1 if (self.network.z_hp[i][j][k][0] > 0 and self.network.Q_cond[i][j][k][0] > self.tol) else 0 for k in range(self.network.S)] for j in range(self.network.J)] for i in range(self.network.I)]
                self.airsink_match = [[[1 if (self.network.z_hp[i][self.network.J][k][0] > 0 and self.network.Q_evap[i][self.network.J][k][0] > self.tol and j==0) else 0 for k in range(self.network.S)] for j in range(self.network.J + 1)] for i in range(self.network.I)]
                self.airsouce_match = [[[1 if (self.network.z_hp[self.network.I][j][k][0] > 0 and self.network.Q_cond[self.network.I][j][k][0] > self.tol and i==0) else 0 for k in range(self.network.S)] for j in range(self.network.J)] for i in range(self.network.I + 1)]

            else: # only recovery HX so no HP's
                self.recovery_match = [[[1 if (self.network.z[i][j][k][0] > 0 and self.network.Q_r[i][j][k][0] > self.tol) else 0 for k in range(self.network.S)] for j in range(self.network.J)] for i in range(self.network.I)]
                self.processHP_match = [[[0 for k in range(self.network.S)] for j in range(self.network.J)] for i in range(self.network.I)]
                self.airsink_match = [[[0 for k in range(self.network.S)] for j in range(self.network.J + 1)] for i in range(self.network.I)]
                self.airsouce_match = [[[0 for k in range(self.network.S)] for j in range(self.network.J)] for i in range(self.network.I + 1)]
            
            self.CU_matches = [1 if (self.network.z_cu[i][0] > 0 and self.network.Q_c[i][0] > self.tol) else 0 for i in range(self.network.I)] # cold utility matches
            self.HU_matches = [1 if (self.network.z_hu[j][0] > 0 and self.network.Q_h[j][0] > self.tol) else 0 for j in range(self.network.J)] # hot utility matches

            # Inject 'ghost' matches for spacing of exclusive matches. Set to 2 so it is distinguished from a common match
            for match in self.exlusive_matches:
                if match[0] == 'recovery':
                    i, j, k = match[1], match[2], match[3]
                    self.recovery_match[i][j][k] = 2    
                elif match[0] == 'HU':
                    j = match[1]
                    self.HU_matches[j] = 2 
                elif match[0] == 'CU':
                    i = match[1]
                    self.CU_matches[i] = 2


        def _calculate_spacing(self):
            """Calculate spacing for streams, matches and stages"""
        
            # Count number of matches in each stage
            if self.draw_HP == True: # also count HP's
                self.stage_count = [sum([1 if self.recovery_match[i][j][k] > 0 or self.processHP_match[i][j][k] > 0 or self.airsink_match[i][self.network.J][k] > 0 or self.airsouce_match[self.network.I][j][k] > 0  else 0 for j in range(self.network.J) for i in range(self.network.I)]) for k in range(self.network.S)] # number of matches in each stage
            else:
                self.stage_count = [sum([1 if self.recovery_match[i][j][k] > 0 else 0 for j in range(self.network.J) for i in range(self.network.I)]) for k in range(self.network.S)] 
            
        
            # Calculate spacing
            self.recovery_length = 20*self.network.S/2 # x-axis distance of recovery stage scaled by number of stages based from 4 stream
            self.stage_start = self.x_start + self.utility_length # x-axis co-ord for first stage boundary
            self.stage_finish =  self.stage_start + self.recovery_length 
            self.x_finish = self.stage_finish + self.utility_length # x-axis co-ord for stream finish
            
            # Match spacing determined by total number of matches divided by the recovery stage length 
            self.match_spacing = self.recovery_length/(sum(self.stage_count)) # x-axis gap between HX's
            self.match_start = self.match_spacing # start dx axis co-ord for first match of the stage from stage boundary
            
            # Count number of branches for a stream in a stage [[H0_S0, H1_S0], [H0_S1, H1_S1]]. Need to also count air matches, but only once per stream hence the j==0 i==0 otherwise it counts multiple time                                   
            if self.draw_HP == True: # also count HP's
                    self.hot_branch_count  = [[sum([1 if (self.recovery_match[i][j][k] > 0) or (self.processHP_match[i][j][k]> 0) 
                                                    or (self.airsink_match[i][self.network.J][k] > 0 and j==0) else 0 for j in range(self.network.J)]) for k in range(self.network.S)] for i in range(self.network.I)]
                    self.cold_branch_count = [[sum([1 if (self.recovery_match[i][j][k] > 0) or (self.processHP_match[i][j][k] > 0) 
                                                    or (self.airsouce_match[self.network.I][j][k] > 0 and i==0) else 0 for i in range(self.network.I)]) for k in range(self.network.S)] for j in range(self.network.J)]
            else:
                    self.hot_branch_count  = [[sum([1 if (self.recovery_match[i][j][k] > 0) else 0 for j in range(self.network.J)]) for k in range(self.network.S)] for i in range(self.network.I)]
                    self.cold_branch_count = [[sum([1 if (self.recovery_match[i][j][k] > 0) else 0 for i in range(self.network.I)]) for k in range(self.network.S)] for j in range(self.network.J)]
              

        def draw_streams(self):
            """Draws streams on grid"""
            
            # Draw cold grid
            for j in range(self.network.J):
                    branches = max([self.cold_branch_count[-1 - j][k] for k in range(self.network.S)]) # count how many branches are needed in each stage and return the max of all stages
                    if branches == 0: # no branches means no recovery matches on the whole stream but still need to add spacing
                        branches = 1

                    self.y_start = self.y_start + self.stream_spacing*branches # add spacing based upon the max number of branches needed for that stage
                    
                    dx = self.x_start - self.x_finish
                    dy = self.y_start - self.y_start
                    
                    self.ax.arrow(self.x_finish, self.y_start, dx, dy*5, head_width=0.25, head_length=0.1*(self.recovery_length/20), lw=5, length_includes_head=True, color='blue') # add arrow
                    self.cold_y_coords.append(self.y_start) # save the line y-coord 
                    
            # Determine how many branches needed for each stream by taking the max (sum(matches in each stage - 1) of each stage), -1 is there since if there is 1 match then 0 branches needed                     
            self.y_start = self.cold_y_coords[-1] + 0.2   
    
            # Draw hot grid
            for i in range(self.network.I):
                    branches = max(max([self.hot_branch_count[-1 - i][k] for k in range(self.network.S)]), 1) # count how many branches are needed in each stage and return the max of all stages. If theres no recovery matches then the branches will be set to 1 via outer max function
                    if branches == 0: # no branches means no recovery matches on the whole stream but still need to add spacing
                        branches = 1
                    
                    self.y_start = self.y_start + self.stream_spacing*branches # add spacing based upon the max number of branches needed for that stage
                    
                                
                    dx = self.x_finish - self.x_start 
                    dy = self.y_start - self.y_start

                    self.ax.arrow(self.x_start, self.y_start, dx, dy*5, head_width=0.25, head_length=0.1*(self.recovery_length/20), lw=5, length_includes_head=True, color='red') # add arrow
                    #self.ax.text(self.x_start - ((self.x_finish - self.x_start)/(20/0.95) +  len(self.network.hot_names[self.network.I - i - 1])*0.075*(self.network.S/2)), self.y_start, self.network.hot_names[self.network.I - i - 1]) # add stream label
                    self.hot_y_coords.append(self.y_start) # save the line y-coord 
                    
            # Determine start points for each grouping of recovery HX's
            boundary = self.stage_start # first stage boundary
            # Loop through other boundaries
            for k in range(self.network.S+1):
                    self.stage_bounaries.append(boundary)
                    boundary_line = Line2D((boundary, boundary), (self.hot_y_coords[-1] + 1, self.cold_y_coords[0] - 1), lw=5., linestyle='dashed', color = 'black')
                    if self.draw_stages == True:
                            self.ax.add_line(boundary_line)

                    if k < self.network.S: # calculate next stage boundary
                        boundary += self.stage_count[k]*self.match_spacing # boundary is as wide as needed to fit the number of HX's in that stage
                    else: # don't calculate next boundary
                        break
                    
        def draw_branches(self):
            """Draws branches on grid in each stage if required"""
            # Displacement distance from boundary
            x_left_vert_in = 0.5 # how far right of the boundary does the vertical line start
            x_right_vert_in = 0.5 # how far left of the boundary does the vertical line start
            
            # Draw cold branches
            for j in range(self.network.J):
                    for k in range(self.network.S):
                        dx_horiz =  1.5*self.match_spacing/5 # x-axis difference between vertical line start and horizontal line start i.e run of the angled line (moved to inside k so dx resets each stage)
                        if self.cold_branch_count[j][k] > 1:
                                count = 2
                                for b in range(self.cold_branch_count[j][k] - 1):
                                        # Plot horizontal branches 
                                        x1_horiz = self.stage_bounaries[k] + x_left_vert_in + dx_horiz # start x point for horizontal line
                                        x2_horiz = self.stage_bounaries[k+1] - x_right_vert_in - dx_horiz # finish x point for horizontal line
                                        horiz_branch_line = Line2D((x1_horiz, x2_horiz), (self.cold_y_coords[-1-j] - count, self.cold_y_coords[-1-j] - count), lw=5.,  color = 'blue', ) # left vertical branch
                                        self.ax.add_line(horiz_branch_line) 
                                        
                                        # Plot angled branch lines                                  
                                        vert_branch_line1 = Line2D((self.stage_bounaries[k] + x_left_vert_in, x1_horiz), (self.cold_y_coords[-1-j], self.cold_y_coords[-1-j] - count), lw=5.,  color = 'blue', ) # left vertical branch
                                        vert_branch_line2 = Line2D((self.stage_bounaries[k+1] - x_right_vert_in, x2_horiz), (self.cold_y_coords[-1-j], self.cold_y_coords[-1-j] - count), lw=5.,  color = 'blue', ) # right vertical branch                                     
                                        self.ax.add_line(vert_branch_line1)    
                                        self.ax.add_line(vert_branch_line2) 

                                        # Change co-ords for next branch
                                        count += self.branch_spacing
                                        dx_horiz -= 0.25*self.match_spacing/5
                                        
            # Draw hot branches
            for i in range(self.network.I):
                    for k in range(self.network.S):
                        dx_horiz =  1.5*self.match_spacing/5 # x-axis difference between vertical line start and horizontal line start i.e run of the angled line
                        if self.hot_branch_count[i][k] > 1:
                                count = 2
                                for b in range(self.hot_branch_count[i][k] - 1): # loop for number of matches on the line (minus 1 for stream line already drawn)
                                        # Plot horizontal branches 
                                        x1_horiz = self.stage_bounaries[k] + x_left_vert_in + dx_horiz # start x point for horizontal line
                                        x2_horiz = self.stage_bounaries[k+1] - x_right_vert_in - dx_horiz # finish x point for horizontal line
                                        horiz_branch_line = Line2D((x1_horiz, x2_horiz), (self.hot_y_coords[-1-i] - count, self.hot_y_coords[-1-i] - count), lw=5.,  color = 'red', ) # left vertical branch
                                        self.ax.add_line(horiz_branch_line) 
                                        
                                        # Plot angled branch lines                                  
                                        vert_branch_line1 = Line2D((self.stage_bounaries[k] + x_left_vert_in, x1_horiz), (self.hot_y_coords[-1-i], self.hot_y_coords[-1-i] - count), lw=5.,  color = 'red', ) # left vertical branch
                                        vert_branch_line2 = Line2D((self.stage_bounaries[k+1] - x_right_vert_in, x2_horiz), (self.hot_y_coords[-1-i], self.hot_y_coords[-1-i] - count), lw=5.,  color = 'red', ) # right vertical branch                                     
                                        self.ax.add_line(vert_branch_line1)    
                                        self.ax.add_line(vert_branch_line2) 

                                        # Change co-ords for next branch
                                        count += self.branch_spacing
                                        dx_horiz -= 0.25*self.match_spacing/5
                                                               
        def draw_recovery_matches(self):
            """Draws recovery matches on grid using line with markers"""
            ## count matches in a stage and count accordingly
            self.match_radius = 50 # radius of HX circle (pixels I think)
            
            # Re-calculate co-ords for matches
            self.match_cords =  [[[[0,1] for k in range(self.network.S)] for j in range(self.network.J + 1)] for i in range(self.network.I + 1)] # y-co-ord for match [i][j][k][yhot,ycod]
            # Set match cold y co-ords
            for k in range(self.network.S):
                    for j in range(self.network.J):
                        branch_number = self.cold_branch_count[j][k] - 1 # reset branch number for each set of hot streams
                        for i in range(self.network.I):
                                if self.recovery_match[i][j][k] > 0 or self.processHP_match[i][j][k] > 0 or self.airsouce_match[self.network.I][j][k] > 0: # check for unit match
                                    if self.cold_branch_count[j][k] > 1: # subtract the number of branch spaces from line co-ords
                                        self.match_cords[i][j][k][1] = self.cold_y_coords[-1-j] - 2*branch_number
                                        branch_number -= 1 # decrease the branch number so the match y co-ord increases
                                    else: # append line co-ord
                                        self.match_cords[i][j][k][1] = self.cold_y_coords[-1-j]
            # Set match hot y co-ords
            for k in range(self.network.S):          
                    for i in range(self.network.I):
                        branch_number = self.hot_branch_count[i][k] - 1 # reset branch number for each set of cold streams
                        for j in range(self.network.J):
                            if self.recovery_match[i][j][k] > 0 or self.processHP_match[i][j][k] > 0 or self.airsink_match[i][self.network.J][k] > 0: # check for unit match
                                if self.hot_branch_count[i][k] > 1: # subtract the number of branch spaces from line co-ords
                                    self.match_cords[i][j][k][0] = self.hot_y_coords[-1-i] - 2*branch_number
                                    branch_number -= 1 # decrease the branch number so the match y co-ord increases
                                else: # append line co-ord
                                    self.match_cords[i][j][k][0] = self.hot_y_coords[-1-i]
                    
            # Draw line with marker
            match_x = self.stage_bounaries[0] + self.match_start/2
            for k in range(self.network.S):
                    for i in range(self.network.I):
                        for j in range(self.network.J):
                                if self.recovery_match[i][j][k] > 0: # add HX match
                                    # modify if match is common
                                    is_common_match = ('recovery', i, j, k) in self.common_matches # check if match is highlighted
                                    is_exclusive_match = ('recovery', i, j, k) in self.exlusive_matches # check if match is exclusive to comparison network
                                    
                                    if is_common_match:
                                        marker_edge = 'lime' 
                                        marker_edge_width = 2.5 
                                        self.ax.add_line(Line2D((match_x, match_x), (self.match_cords[i][j][k][0], self.match_cords[i][j][k][1]), lw=8., color='lime', zorder=1))  # draw thicker line behind it
                                    elif is_exclusive_match:
                                        marker_edge = 'gold' 
                                        marker_edge_width = 2.5    
                                        self.ax.add_line(Line2D((match_x, match_x), (self.match_cords[i][j][k][0], self.match_cords[i][j][k][1]), lw=8., color='gold', zorder=1))  # draw thicker line behind it
                                    
                                    else:   
                                        marker_edge = 'black' 
                                        marker_edge_width = 1.0  
                            
                                    # draw match line
                                    recovery_HX = Line2D((match_x, match_x), (self.match_cords[i][j][k][0], self.match_cords[i][j][k][1]), lw=5., color = 'black', marker='.', markersize=self.match_radius, markerfacecolor='black', markeredgecolor=marker_edge, markeredgewidth=marker_edge_width) # create line
                                    self.ax.add_line(recovery_HX) # add line to plot
                                    match_x += self.match_spacing # ensure that next match in stage is made to the right of the current match
                                    
                                elif self.processHP_match[i][j][k] > 0: # add process HP match
                                    heatpump_HX = Line2D((match_x, match_x), (self.match_cords[i][j][k][0], self.match_cords[i][j][k][1]), lw=5., color = 'orange', marker='.', markersize=self.match_radius, markerfacecolor='orange', markeredgecolor='orange') # create line
                                    self.ax.add_line(heatpump_HX) # add line to plot
                                    match_x += self.match_spacing # ensure that next match in stage is made to the right of the current match
                                elif self.airsink_match[i][self.network.J][k] > 0: # air sink HP
                                    sink_heatpump_HX = Line2D((match_x, match_x), (self.match_cords[i][j][k][0], self.match_cords[i][j][k][0]), lw=5., color = 'aqua', marker='.', markersize=self.match_radius, markerfacecolor='aqua', markeredgecolor='aqua') # create circle
                                    self.ax.add_line(sink_heatpump_HX) # add line to plot
                                    match_x += self.match_spacing # ensure that next match in stage is made to the right of the current match
                                elif self.airsouce_match[self.network.I][j][k] > 0: # air source HP
                                    source_heatpump_HX = Line2D((match_x, match_x), (self.match_cords[i][j][k][1], self.match_cords[i][j][k][1]), lw=5., color = 'tomato', marker='.', markersize=self.match_radius, markerfacecolor='tomato', markeredgecolor='tomato') # create circle
                                    self.ax.add_line(source_heatpump_HX) # add line to plot
                                    match_x += self.match_spacing # ensure that next match in stage is made to the right of the current match
                    match_x = self.stage_bounaries[k+1] + self.match_start/2 # ensure that matches in next stage start to the right of the current stage boundary - could take this out and change stage spacing to do repeating pattern
                
        def draw_utility_match(self):
            """Draws utility matches on grid using circle"""

            self.match_HU_x = self.x_start + (self.stage_start - self.x_start)/2 # draw in middle of utility stage

            # Add hot utility
            for j in range(self.network.J):
                    if self.HU_matches[j] > 0: # add hot utility
                        is_common_match = ('HU', j) in self.common_matches # check if match is highlighted
                        is_exclusive_match = ('HU', j) in self.exlusive_matches # check if match is exclusive to comparison network
                        if is_common_match:
                            marker_edge = 'lime' 
                            marker_edge_width = 2.5 
                            #self.ax.add_line(Line2D((self.match_HU_x, self.match_HU_x), (self.cold_y_coords[-1-j], self.cold_y_coords[-1-j]), lw=8., color='lime', zorder=1))  # draw thicker line behind it
                        elif is_exclusive_match:
                            marker_edge = 'gold' 
                            marker_edge_width = 2.5    
                            #self.ax.add_line(Line2D((self.match_HU_x, self.match_HU_x), (self.cold_y_coords[-1-j], self.cold_y_coords[-1-j]), lw=8., color='gold', zorder=1))  # draw thicker line behind it
                        
                        else:   
                            marker_edge = 'red' 
                            marker_edge_width = 1.0   
                        
                        self.ax.add_line(Line2D((self.match_HU_x, self.match_HU_x), (self.cold_y_coords[-1-j], self.cold_y_coords[-1-j]), lw=5., color = 'red', marker='.', markersize=self.match_radius, markerfacecolor='red', markeredgecolor=marker_edge, markeredgewidth=marker_edge_width ))
                       

            ## self.stage_boundaries[-1] should be calculated from total length of all matches + spacing
            self.match_CU_x = self.stage_bounaries[-1] + (self.x_finish - self.stage_bounaries[-1])/2  # draw in middle of utility stage
            
            # Add cold utility
            for i in range(self.network.I):
                    if self.CU_matches[i] > 0: # add cold utility
                        is_highlight = ('CU', i) in self.common_matches # check if match is highlighted
                        marker_edge = 'lime' if is_highlight else 'blue'
                        marker_edge_width = 2.5 if is_highlight else 1.0
                        self.ax.add_line(Line2D((self.match_CU_x, self.match_CU_x), (self.hot_y_coords[-1-i], self.hot_y_coords[-1-i]), lw=5., color = 'blue', marker='.', markersize=self.match_radius, markerfacecolor='blue', markeredgecolor=marker_edge, markeredgewidth=marker_edge_width))
                        
            
       
        def add_duties(self):
            """Adds heat transfer duty above HX match line"""
            # Scale text locations based off size of axis compared to 4 streams
            self.x_offset = (self.x_finish - self.x_start)/(20/0.5)
            self.y_offset = (self.hot_y_coords[-1] - self.cold_y_coords[-1])/(8/0.3) #increasing decimal denominator reduces the offset
            match_x = self.stage_bounaries[0] + self.match_start/2
            # Add recovery duty label
            for k in range(self.network.S):
                    for i in range(self.network.I):
                        for j in range(self.network.J):
                                if self.recovery_match[i][j][k] == 1: # add HX match
                                        self.ax.text(match_x - self.x_offset*1.5, self.match_cords[i][j][k][1] - self.y_offset*1.85, "{:.2f} MW".format(self.network.Q_r[i][j][k][0]/1000), fontsize=self.duty_font_size, color='purple') # add duty label in MW formatted to 2DP
                                        match_x += self.match_spacing # ensure that next match in stage is made to the right of the current match
                                elif self.processHP_match[i][j][k] > 0: # process HP match
                                        self.ax.text(match_x - self.x_offset, self.match_cords[i][j][k][0] + self.y_offset, "{:.2f} MW".format(self.network.Q_evap[i][j][k][0]/1000), fontsize=self.size_of_font) # add evap label in MW formatted to 2DP
                                        self.ax.text(match_x - self.x_offset, self.match_cords[i][j][k][1] - self.y_offset*1.75, "{:.2f} MW".format(self.network.Q_cond[i][j][k][0]/1000), fontsize=self.size_of_font) # add cond label in MW formatted to 2DP
                                        match_x += self.match_spacing # ensure that next match in stage is made to the right of the current match
                                elif self.airsink_match[i][self.network.J][k] > 0: # air sink HP
                                        self.ax.text(match_x - self.x_offset, self.match_cords[i][j][k][0] + self.y_offset, "{:.2f} MW".format(self.network.Q_evap[i][self.network.J][k][0]/1000), fontsize=self.size_of_font) # add duty label in MW formatted to 2DP
                                        match_x += self.match_spacing # ensure that next match in stage is made to the right of the current match
                                elif self.airsouce_match[self.network.I][j][k] > 0: # air source HP
                                        self.ax.text(match_x - self.x_offset, self.match_cords[i][j][k][1] - self.y_offset*1.85, "{:.2f} MW".format(self.network.Q_cond[self.network.I][j][k][0]/1000), fontsize=self.size_of_font) # add duty label in MW formatted to 2DP
                                        match_x += self.match_spacing # ensure that next match in stage is made to the right of the current match
                    match_x = self.stage_bounaries[k+1] + self.match_start/2 # ensure that matches in next stage start to the right of the current stage boundary - could take this out and change stage spacing to do repeating pattern

            # Add hot utility duty label
            for j in range(self.network.J):
                    if self.network.z_hu[j][0] > 0 and self.network.Q_h[j][0] > self.tol: # add hot utility
                        self.ax.text(self.match_HU_x - self.x_offset/2, self.cold_y_coords[-1-j] - self.y_offset*1.85, "{:.2f} MW".format(self.network.Q_h[j][0]/1000), fontsize=self.duty_font_size, color='purple') # add duty label in MW formatted to 2DP
            
            # Add cold utility duty label
            for i in range(self.network.I):
                    if self.network.z_cu[i][0] > 0 and self.network.Q_c[i][0] > self.tol: # add cold utility
                        self.ax.text(self.match_CU_x - self.x_offset*2, self.hot_y_coords[-1-i] - self.y_offset*1.85, "{:.2f} MW".format(self.network.Q_c[i][0]/1000), fontsize=self.duty_font_size, color='purple') # add duty label in MW formatted to 2DP


        def add_temps(self, non_iso):
            """Adds heat transfer duty above HX match line"""
            # Scale text locations based off size of axis compared to 4 streams
            self.x_offset1 = (self.x_finish - self.x_start)/(20/0.2)
            self.x_offset2 = (self.x_finish - self.x_start)/(20/0.95)
            self.hot_y_offset = (self.hot_y_coords[-1] - self.cold_y_coords[-1])/(8/0.1) # distance between the text and stream y-axis for hot streams scaled for the distance of 4 streams
            self.cold_y_offset = (self.hot_y_coords[-1] - self.cold_y_coords[-1])/(8/0.2) # distance between the text and stream y-axis for hot streams scaled for the distance of 4 streams

            match_x = self.stage_bounaries[0] + self.match_start/2
            format_str = r"{:.0f} $^\circ$C" # format string for temperature labels
            # Add recovery and process HP temperatures
            for k in range(self.network.S):
                    for i in range(self.network.I):
                        for j in range(self.network.J):
                                if self.recovery_match[i][j][k] == 1 or self.processHP_match[i][j][k] > 0 or self.airsink_match[i][self.network.J][k] > 0 or self.airsouce_match[self.network.I][j][k] > 0: # add label if there is any match present
                                        if non_iso == True: # use branch temperatures
                                                self.ax.text(match_x  + self.x_offset1, self.match_cords[i][j][k][0] + self.hot_y_offset, format_str.format(self.network.T_h_out_x[i][j][k][0] - 273.15), fontsize=self.temp_font_size) # add hot outlet temp above  HX since branch may cut in below
                                                self.ax.text(match_x - self.x_offset2, self.match_cords[i][j][k][1] + self.cold_y_offset/2 , format_str.format(self.network.T_c_out_y[j][i][k][0]-  273.15), fontsize=self.temp_font_size) # add cold outlet temp below HX since branch may cut in above
                                        else: # use stage boundary temperatures
                                                if self.recovery_match[i][j][k] > 0 or self.processHP_match[i][j][k] > 0 : # match between two streams so plot temps on both streams
                                                    self.ax.text(match_x  + self.x_offset1, self.match_cords[i][j][k][0] + self.hot_y_offset, format_str.format(self.network.T_h[i][k + 1][0] - 273.15), fontsize=self.temp_font_size) # add hot outlet temp above  HX since branch may cut in below
                                                    self.ax.text(match_x - self.x_offset2, self.match_cords[i][j][k][1] + self.cold_y_offset/2, format_str.format(self.network.T_c[j][k][0]-  273.15), fontsize=self.temp_font_size) # add cold outlet temp below HX since branch may cut in above
                                                elif self.airsink_match[i][self.network.J][k] > 0: # air sink HP, plot only hot outlet
                                                    self.ax.text(match_x  + self.x_offset1, self.match_cords[i][j][k][0] + self.hot_y_offset, format_str.format(self.network.T_h[i][k + 1][0] - 273.15), fontsize=self.temp_font_size)
                                                elif self.airsouce_match[self.network.I][j][k] > 0: # air source HP, plot only cold outler
                                                    self.ax.text(match_x - self.x_offset2, self.match_cords[i][j][k][1] + self.cold_y_offset/2, format_str.format(self.network.T_c[j][k][0]-  273.15), fontsize=self.temp_font_size) # add cold outlet temp below HX since branch may cut in above
                                        match_x += self.match_spacing # ensure that next match in stage is made to the right of the current match
                                
                    match_x = self.stage_bounaries[k+1] + self.match_start/2 # ensure that matches in next stage start to the right of the current stage boundary - could take this out and change stage spacing to do repeating pattern
            
            # Add cold stream target and supply temps
            for j in range(self.network.J):
                    if self.network.z_hu[j][0] > 0 and self.network.Q_h[j][0] > self.tol: # if utility used on stream then add outlet temp, otherwise its already plotted with recovery unit
                        self.ax.text(self.match_HU_x - self.x_offset2*1.25, self.cold_y_coords[-1-j] + self.cold_y_offset/2, format_str.format(self.network.T_c_out[j]-  273.15), fontsize=self.temp_font_size)
                    # add cold stream inlet temp
                    self.ax.text(self.x_finish - self.x_offset , self.cold_y_coords[-1-j] + self.cold_y_offset/2, format_str.format(self.network.T_c_in[j]-  273.15), fontsize=self.temp_font_size)
                        

            # Add hot stream target and supply temps
            for i in range(self.network.I):
                    if self.network.z_cu[i][0] > 0 and self.network.Q_c[i][0] > self.tol: # if utility used on stream then add outlet temp, otherwise its already plotted with recovery unit
                        self.ax.text(self.match_CU_x + self.x_offset1*2, self.hot_y_coords[-1-i] + self.hot_y_offset, format_str.format(self.network.T_h_out[i]-  273.15), fontsize=self.temp_font_size)
                    # add hot stream inlet temp
                    self.ax.text(self.x_start, self.hot_y_coords[-1-i] + self.hot_y_offset, format_str.format(self.network.T_h_in[i]-  273.15), fontsize=self.temp_font_size)

        def plot_setup(self):
            # Plot stream names (backwards since co-ords list is backwards)
            cold_stream_names = [f'C{j+1}' for j in reversed(range(self.network.J))]
            hot_stream_names = [f'H{i+1}' for i in reversed(range(self.network.I))]
            self.ax.set_yticks(self.hot_y_coords+self.cold_y_coords, hot_stream_names+cold_stream_names)  
           
            self.ax.set_xticks([])  # Command for hiding y-axis
            self.ax.tick_params(axis='y', which='major', labelsize=self.size_of_font)
            
            #Remove the spines (black borders)
            self.ax.spines['top'].set_visible(False)
            self.ax.spines['bottom'].set_visible(False)
            self.ax.spines['left'].set_visible(False)
            self.ax.spines['right'].set_visible(False)
            
            # Remove minor tickmarks from y-axis
            self.ax.tick_params(left = False)
            # Move the y-axis spine closer to the start of the x-axis
            self.ax.spines['left'].set_position(('data', -0.2))
            self.ax.margins(x=0.005, tight=True) # allow 0.5% gap between axis and line
            # Adjust the margins to shift the figure to the right
            self.fig.tight_layout()
            
        def show(self):
            """Shows the grid diagram"""
    
            self.fig.show()
        
        def save(self, path='grid_diagram.png'):
            """Saves the grid diagram to a file"""
            self.fig.savefig(path, bbox_inches='tight', dpi=100)
        
