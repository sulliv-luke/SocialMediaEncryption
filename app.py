import streamlit as st                                                                                                                                                                        
from pages import dashboard_page, explore_page, group_management_page, login_page, my_posts_page, signup_page

# Remove menu and footer
# =======================
hide_streamlit_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True) 
# =======================


def main():
    st.sidebar.title("Navigation")
    if 'current_user' in st.session_state and st.session_state['current_user']:
        page = st.sidebar.radio("Go to", ("Dashboard", "Group Management", "Explore", "My Posts", "Logout"))
        
        if page == "Dashboard":
            dashboard_page()
        elif page == "Explore":
            explore_page(st.session_state['current_user']['uid'])
        elif page == "Group Management":
            group_management_page()
        elif page == "My Posts":
            my_posts_page(st.session_state['current_user']['uid'])
        elif page == "Logout":
            del st.session_state['current_user']
            st.experimental_rerun()
    else:
        page = st.sidebar.radio("Go to", ("Login", "Sign Up"))
        if page == "Login":
            login_page()
        elif page == "Sign Up":
            signup_page()

if __name__ == "__main__":
    main()
