import React, { createContext, useContext, useState, useEffect } from 'react';
import { login as apiLogin } from './api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    // Fix: Remove hardcoded true (security bypass)
    const [isAuthenticated, setIsAuthenticated] = useState(!!localStorage.getItem('access_token'));


    const login = async (username, password) => {
        await apiLogin(username, password);
        setIsAuthenticated(true);
    };

    const logout = () => {
        localStorage.removeItem('access_token');
        setIsAuthenticated(false);
    };

    return (
        <AuthContext.Provider value={{ isAuthenticated, login, logout }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    return useContext(AuthContext);
}
